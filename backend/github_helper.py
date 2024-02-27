import os
import subprocess
import time

import requests
import json


from dotenv import load_dotenv

load_dotenv()


class GitHubHelper:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.branch_name = f"leaping-fix-{int(time.time())}"
        self.repo_owner = "leapingio"
        self.repo_name = "demo"
        self.commit_message = "Fix NoneType error being"
        self.title = "FIX: Leaping Error 33 - NoneType Error"
        self.body = "This PR fixes the NoneType error that was being thrown when the leave request was created on a leap year"

    def create_branch_and_push(self):
        subprocess.run(["git", "checkout", "-b", self.branch_name])
        subprocess.run(["git", "add", "backend/example.py"])
        subprocess.run(["git", "commit", "-m", "Fix Leaping Error"])
        subprocess.run(["git", "push", "origin", self.branch_name])

    def create_pull_request(self, repo_owner, repo_name):
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        data = {
            "title": self.title,
            "body": self.body,
            "head": self.branch_name,
            "base": "main",  # TODO: make user configurable or somehow figure out how to make this the protected branch
        }
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 201:
            print("Pull request created successfully.")
        else:
            print("Failed to create pull request. Status code:", response.status_code)
            print("Response:", response.text)

        return json.loads(response.content)["html_url"]
