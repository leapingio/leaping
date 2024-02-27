import asyncio
import dataclasses
import json
from typing import Optional

from backend.web_socket_manager import WebSocketManager


@dataclasses.dataclass
class EditorOperation:
    type: str
    lineno: int
    step: int
    text: Optional[str] = None
    end: Optional[bool] = False

    def to_json(self):
        operation_dict = dataclasses.asdict(self)
        return json.dumps(operation_dict, ensure_ascii=False)


class EditorSocketWrapper:
    def __init__(self, socket_manager: WebSocketManager):
        self.socket_manager = socket_manager  # Consider just consolidating these two classes, maybe have one for the terminal and one for the other thing

    def notify_frontend_of_delete(self, line_number, step):
        operation = EditorOperation("d", lineno=line_number, step=step, end=False)
        self.socket_manager.post_message(operation.to_json())

    def notify_frontend_of_insert(self, line_number, indented_line, step, end=False):
        operation = EditorOperation(
            "i", lineno=line_number, step=step, text=indented_line, end=end
        )
        self.socket_manager.post_message(operation.to_json())

    def notify_frontend_of_print(self, message, step, format=""):
        self.socket_manager.post_message(
            json.dumps({"type": "p", "text": message, "step": step, "format": format})
        )

    def notify_frontend_of_root_cause(self, message, step):
        self.socket_manager.post_message(
            json.dumps({"type": "p", "text": message, "step": step})
        )

    def check_for_fe_commands(self):
        # Checks if the frontend has sent commands over the websocket
        try:
            command = self.socket_manager.command_queue.get_nowait()
            return command
        except asyncio.QueueEmpty:
            pass

        return False
