import dataclasses
import os

from openai import OpenAI

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")


@dataclasses.dataclass
class Message:
    role: str
    content: str
    type: str

    def to_gpt_message(self):
        return {
            "role": self.role,
            "content": self.content,
        }


class LLMWrapper:
    def __init__(self, model_name, temperature, socket_wrapper, messages=[]):
        self.model_name = model_name
        self.temperature = temperature
        self.client = OpenAI()
        self.messages = messages
        self.step_to_message = {}
        self.socket_wrapper = socket_wrapper
        self.kill_switch = False

    def _filter_messages(self, message_type):
        # def same_type_filter(message, idx):
        #     return self.messages[idx].type == message_type

        single_message_filters = []

        def not_most_recent_of_type_filter(message, idx, messages):
            if (
                message.type == "root_cause"
            ):  # we want GPT to always have context over the previous thinking for rcs
                return True
            return not any(
                message.type == subsequent_message.type
                for subsequent_message in messages[idx + 1 :]
            )

        multi_message_filters = [not_most_recent_of_type_filter]

        cleaned_messages = []

        for idx, message in enumerate(self.messages):
            if (
                idx == len(self.messages) - 1
            ):  # always include the last message (the one that we're trying to send)
                cleaned_messages.append(message)
                break

            if not all(f(message, idx, self.messages) for f in multi_message_filters):
                continue
            if not all(f(message, idx) for f in single_message_filters):
                continue

            cleaned_messages.append(message)

        return cleaned_messages

    def _format_messages(self, messages):
        return [message.to_gpt_message() for message in messages]

    def add_message(self, role, prompt, step, message_type=""):
        self.socket_wrapper.notify_frontend_of_print(prompt, step, format="to_gpt")
        message = Message(role, prompt, message_type)
        self.messages.append(message)

    def chat_completion(self, step):
        if self.kill_switch:
            return "Over limit"

        messages = self.messages
        if self.messages:
            messages = self._filter_messages(self.messages[-1].type)

        formatted_messages = self._format_messages(messages)

        response = self.client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=formatted_messages,
            temperature=self.temperature,
        )
        response_content = response.choices[0].message.content

        if response.usage.total_tokens > 10000:
            self.kill_switch = True

        self.socket_wrapper.notify_frontend_of_print(
            response_content, step, format="from_gpt"
        )

        self.messages.append(Message("assistant", response_content, messages[-1].type))
        self.step_to_message[step] = len(self.messages) - 1

        return response_content

    def get_messages_of_type(self, message_type: str) -> list[Message]:
        return [message for message in self.messages if message.type == message_type]
