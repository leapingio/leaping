import os

from openai import OpenAI


class GPT:
    def __init__(self, model_name, temperature):
        self.model_name = model_name
        self.temperature = temperature
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = OpenAI(api_key=api_key)
        self.messages = []

    def add_message(self, role, prompt):
        self.messages.append({"role": role, "content": prompt})

    def chat_completion(self, stream=False):
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self.messages,
            temperature=self.temperature,
            stream=stream,
        )
        if stream:
            return response
        response_content = response.choices[0].message.content
        self.add_message("assistant", response_content)

        return response_content

