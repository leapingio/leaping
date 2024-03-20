import os

from openai import OpenAI
from leaping_server_wrapper import LeapingServer


class GPT:
    def __init__(self, model_name, temperature, in_server_mode=False):
        self.model_name = model_name
        self.temperature = temperature
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = OpenAI(api_key=api_key)
        self.messages = []
        self.in_server_mode = in_server_mode

    def add_message(self, role, prompt):
        self.messages.append({"role": role, "content": prompt})

    def chat_completion(self, stream=False):
        if self.in_server_mode:
            for chunk in LeapingServer.process_gpt_request(self.messages):
                yield chunk.decode("utf-8")

            return

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self.messages,
            temperature=self.temperature,
            stream=stream,
        )
        if stream:
            for chunk in response:
                if chunk_delta := chunk.choices[0].delta.content:
                    yield chunk_delta

            return

        response_content = response.choices[0].message.content
        self.add_message("assistant", response_content)

        return response_content
