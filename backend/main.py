from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.editor_socket_wrapper import EditorSocketWrapper
from backend.web_socket_manager import WebSocketManager

from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


manager = WebSocketManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)


class RunRequest(BaseModel):
    traceback: str


@app.post("/run")
def run(request: RunRequest):
    from .runscript import run

    traceback = request.traceback

    socket_wrapper = EditorSocketWrapper(manager)

    return run(socket_wrapper, traceback)
