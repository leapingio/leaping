from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import supabase

from gpt import GPT

app = FastAPI()

# Define a Pydantic model for the request data
class TelemetryData(BaseModel):
    email: str
    username: str
    ip: str
    messages: list[dict[str, str]]


# Dummy function to simulate database check
def should_rate_limit(email: str, ip: str) -> bool:
    users = supabase.from_('users').select().eq('email', email).execute()
    if users:
        credits_used = users['credits_used']
        if credits_used < 5:
            return False

    supabase.table('pytest-leaping').select("*").execute()

async def chat_generator(messages: list[dict[str, str]], email):
    # Your logic to initiate the chat and stream responses
    # This placeholder simulates generating and streaming data
    gpt = GPT("gpt-4-0125-preview", 0.5)
    gpt.messages = messages
    total_tokens = 0
    cost_per_token = 10 / 1000000

    response = gpt.chat_completion(stream=True)
    for chunk in response:
        if message := chunk.choices[0].delta.content:
            yield message.encode('utf-8')
            await asyncio.sleep(.1)

    total_cost = response['usage']['total_tokens'] * cost_per_token
    supabase.table('pytest-leaping').upsert({"email": email, "credits_used": total_cost}, returning="minimal").execute()

@app.post("/process-gpt-request/")
async def process_gpt_request(data: TelemetryData):
    # Check value from database using the validated request data
    if should_rate_limit(data.email, data.ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return StreamingResponse(chat_generator(data.messages), media_type="text/event-stream")


res = should_rate_limit("some-email", "some-ip")