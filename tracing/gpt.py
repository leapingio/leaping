import dataclasses
import os

from openai import OpenAI

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

class GPT:
    def __init__(self, model_name, temperature):
        self.model_name = model_name
        self.temperature = temperature
        self.client = OpenAI()
        self.messages = []

    def add_message(self, role, prompt):
        self.messages.append({"role": role, "content": prompt})

    def chat_completion(self):
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self.messages,
            temperature=self.temperature,
        )
        response_content = response.choices[0].message.content
        self.add_message("assistant", response_content)

        return response_content

