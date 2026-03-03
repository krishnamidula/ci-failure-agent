import os
import requests
import zipfile
import io
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
    print("🔥 VERSION 3 - LLM ACTIVE 🔥")
    payload = await request.json()

    print("Received webhook")

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
           log_snippet = analyze_logs(logs)
           analysis = analyze_with_llm(log_snippet)
           send_slack_message(f"🚨 CI Failed in {repo}\n\n{analysis}")
        else:
            send_slack_message(f"🚨 CI Failed in {repo}\n\nCould not fetch logs.")

    return {"status": "received"}


def fetch_workflow_logs(owner, repo, run_id):
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("Failed to download logs:", response.text)
        return None

    try:
        # GitHub returns logs as ZIP
        zip_bytes = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_bytes) as z:
            combined_logs = ""
            for file_name in z.namelist():
                with z.open(file_name) as f:
                    combined_logs += f.read().decode("utf-8", errors="ignore")
            print("Logs extracted successfully")
            return combined_logs[:-6000]  # limit size
    except Exception as e:
        print("Error extracting logs:", e)
        return None


def analyze_logs(log_text):
    lines = log_text.splitlines()

    # Reverse search for real failure indicators
    failure_indicators = [
        "Traceback",
        "AssertionError",
        "ModuleNotFoundError",
        "SyntaxError",
        "FAILED",
        "ERROR",
        "Exception"
    ]

    # Search from bottom (most recent lines first)
    for i in range(len(lines) - 1, -1, -1):
        for keyword in failure_indicators:
            if keyword in lines[i]:
                start = max(i - 15, 0)
                end = min(i + 25, len(lines))
                return "\n".join(lines[start:end])

    # If nothing found, return last 300 lines
    return "\n".join(lines[-300:])
def analyze_with_llm(log_snippet):
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system",
                "content": "You are a DevOps expert. Identify the root cause of CI failure and suggest a clear fix."
            },
            {
                "role": "user",
                "content": f"Analyze this CI log snippet and provide:\n1. Root Cause\n2. Suggested Fix\n\nLogs:\n{log_snippet}"
            }
        ],
        "temperature": 0.2,
        "max_tokens": 400,
    }

    try:
        response = requests.post(url, headers=headers, json=data)

        print("Groq status:", response.status_code)

        if response.status_code != 200:
            print("Groq error:", response.text)
            return "AI analysis failed."

        result = response.json()
        return result["choices"][0]["message"]["content"]

    except Exception as e:
        print("Groq Exception:", str(e))
        return "AI analysis crashed."
def send_slack_message(message):
    data = {"text": message}

    response = requests.post(SLACK_WEBHOOK_URL, json=data)

    if response.status_code == 200:
        print("Slack notification sent")
    else:
        print("Slack error:", response.text)