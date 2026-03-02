import os
import requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


@app.get("/")
async def root():
    return {"message": "Server running"}


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()

    print("Received payload")

    # Check if this is workflow_run event and completed
    if (
        payload.get("action") == "completed"
        and payload.get("workflow_run", {}).get("conclusion") == "failure"
    ):
        print("CI FAILURE DETECTED")

        workflow_run = payload["workflow_run"]
        repo = payload["repository"]["name"]
        owner = payload["repository"]["owner"]["login"]
        run_id = workflow_run["id"]

        logs = fetch_workflow_logs(owner, repo, run_id)

        if logs:
            analysis = analyze_logs(logs)
            send_slack_message(
                f"🚨 CI Failed in {repo}\n\n{analysis}"
            )

    return {"status": "received"}


def fetch_workflow_logs(owner, repo, run_id):
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print("Logs fetched successfully")
        return response.text
    else:
        print("Failed to fetch logs:", response.text)
        return None


def analyze_logs(log_text):
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "mistralai/mistral-7b-instruct:free",
        "messages": [
            {
                "role": "system",
                "content": "You analyze CI logs and explain the root cause clearly and briefly."
            },
            {
                "role": "user",
                "content": log_text[:5000]  # limit size
            }
        ],
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        return result["choices"][0]["message"]["content"]
    else:
        print("OpenRouter error:", response.text)
        return "Could not analyze logs."


def send_slack_message(message):
    data = {
        "text": message
    }

    response = requests.post(SLACK_WEBHOOK_URL, json=data)

    if response.status_code == 200:
        print("Slack notification sent")
    else:
        print("Slack error:", response.text)