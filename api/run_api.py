import httpx
import asyncio

import requests


def main():
    # Endpoint URL
    url = "http://127.0.0.1:8000/process-gpt-request/"

    # JSON payload
    json_data = {
        "email": "user@example.com",
        "ip": "192.168.1.1",
        "username": "user",
        "messages": [
        {
            "role": "system",
            "content": "Please write a two paragraph response, consisting of two sentences each, on whatever the topic the user supplies is"
        },
        {
            "role": "user",
            "content": "Conspiracy theories about Antarctica",
        }
    ],
    }
    with requests.post(url, json=json_data, stream=True) as request:
        for chunk in request.iter_content():
            print(chunk.decode('utf-8'), end="")

# Run the main function in an event loop
if __name__ == "__main__":
    main()