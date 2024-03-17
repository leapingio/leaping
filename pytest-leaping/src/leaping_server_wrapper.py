import dataclasses
import subprocess
import socket

import requests

LEAPING_BASE_URL = "http://127.0.0.1:8000/"


@dataclasses.dataclass
class ProcessGPTRequest:
    ip: str
    username: str
    email: str
    messages: list[dict[str, str]]

    def to_json(self):
        return dataclasses.asdict(self)


class LeapingServer:
    @staticmethod
    def process_gpt_request(messages: list[dict[str, str]]):
        # TODO: move to a helper metho
        output = subprocess.check_output(["git", "config", "--global", "user.name"])
        username = output.decode().strip()
        output = subprocess.check_output(["git", "config", "--global", "user.email"])
        email = output.decode().strip()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to a known host to get the IP address
        ip_address = s.getsockname()[0]
        s.close()

        request = ProcessGPTRequest(
            ip=ip_address,
            username=username,
            email=email,
            messages=messages
        ).to_json()

        try:
            res = requests.post(url=f"{LEAPING_BASE_URL}process-gpt-request", json=request, stream=True)
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return

        for chunk in res:
            try:
                yield chunk
            except Exception as e:
                print(e)

#
# messages = [
#     {
#         "role": "system",
#         "content": "Please write a two paragraph response, consisting of two sentences each, on whatever the topic the user supplies is"
#     },
#     {
#         "role": "user",
#         "content": "Conspiracy theories about Antarctica",
#     }
# ]
#
# res = LeapingServer.process_gpt_request(messages)
# for chunk in res:
#     print(chunk.decode('utf-8'), end="")
#
