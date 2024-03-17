import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import supabase
from supabase import create_client
from fastapi_cors import CORS

from gpt import GPT

app = FastAPI()
url = os.getenv('SUPABASE_URL')
api_key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, api_key)

origins = ["*"]

app.add_middleware(
    CORS,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Define a Pydantic model for the request data
class TelemetryData(BaseModel):
    email: str
    username: str
    ip: str
    messages: list[dict[str, str]]


# Dummy function to simulate database check
def should_rate_limit(data: TelemetryData) -> bool:
    # should this also check for ip address/username?
    data = (supabase.table('pytest-leaping').select("*")
            .eq('email', data.email)
            .eq('username', data.username)
            .eq('ip', data.ip)
            .execute())
    result = data.data

    return result and result[0]['credits_used'] > 4.70


@app.get("/healthcheck")  # required for fly.io
def read_root():
    return {"status": "ok"}


async def chat_generator(data: TelemetryData):
    # Your logic to initiate the chat and stream responses
    # This placeholder simulates generating and streaming data
    gpt = GPT("gpt-4-0125-preview", 0.5)
    gpt.messages = data.messages
    total_tokens = 0
    cost_per_token = 10 / 1000000

    response = gpt.chat_completion(stream=True)
    for chunk in response:
        if message := chunk.choices[0].delta.content:
            yield message.encode('utf-8')
            await asyncio.sleep(.1)

    # calculate the token cost manually :(
    total_cost = 0.3
    # Look up the existing row by email, TODO: look up by email, ip, and username
    result = supabase.table('pytest-leaping').select('credits_used').eq('email', data.email).execute()
    if result.data:
        # If the row exists, add the new cost to the existing credits_used value
        existing_credits_used = result.data[0]['credits_used']
        total_cost += existing_credits_used

    # Upsert the row with the provided values
    data = {
        'username': data.username,
        'email': data.email,
        'ip': data.ip,
        'credits_used': total_cost
    }
    supabase.table('pytest-leaping').upsert(data, returning='minimal').execute()


@app.post("/process-gpt-request/")
async def process_gpt_request(data: TelemetryData):
    # Check value from database using the validated request data
    if should_rate_limit(data):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return StreamingResponse(chat_generator(data), media_type="text/event-stream")
