import asyncio
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.connection = None
        self.message_queue = asyncio.Queue()
        self.command_queue = asyncio.Queue()  # TODO: make this name better

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connection = websocket
        await asyncio.gather(self.receive_messages(), self.process_queue_messages())

    async def receive_messages(self):
        try:
            while True:
                message = await self.connection.receive_text()
                self.command_queue.put_nowait(message)
        except Exception as e:
            print(f"Error receiving message: {e}")

    async def send_message(self, message: str):
        if self.connection:
            try:
                await self.connection.send_text(message)
            except Exception as e:
                print(f"Error sending message: {e}")

    async def process_queue_messages(self):
        while True:
            message = await self.message_queue.get()
            await self.send_message(message)

    def post_message(self, message: str):
        self.message_queue.put_nowait(message)
