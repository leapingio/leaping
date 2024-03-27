import abc
import dataclasses
import os

import ollama
from openai import OpenAI


@dataclasses.dataclass
class LLM(abc.ABC):
    model_name: str
    messages: list[dict[str, str]] = dataclasses.field(default_factory=list)

    def add_message(self, role, prompt):
        self.messages.append({"role": role, "content": prompt})

    @abc.abstractmethod
    def chat_completion(self, stream=False):
        pass


@dataclasses.dataclass
class Ollama(LLM):
    def chat_completion(self, stream=False):
        response = ollama.chat(
            model='llama2',
            messages=self.messages,
            stream=stream,
        )

        if stream:
            for chunk in response:
                yield chunk['message']['content']

        return response


@dataclasses.dataclass
class GPT(LLM):
    temperature: float = 0.1

    def __post_init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = OpenAI(api_key=api_key)

    def chat_completion(self, stream=False):
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
