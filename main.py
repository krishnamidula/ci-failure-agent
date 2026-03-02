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
            analysis = analyze_logs(logs)
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
            return combined_logs[:8000]  # limit size
    except Exception as e:
        print("Error extracting logs:", e)
        return None


def analyze_logs(log_text):
    # Simple failure detection instead of LLM
    lines = log_text.splitlines()

    error_lines = []

    for line in lines:
        if "error" in line.lower() or "failed" in line.lower():
            error_lines.append(line)

    if not error_lines:
        return "CI failed but no obvious error message found."

    summary = "\n".join(error_lines[:5])  # show first 5 errors
    return f"Detected error lines:\n\n{summary}"
    


def send_slack_message(message):
    data = {"text": message}

    response = requests.post(SLACK_WEBHOOK_URL, json=data)

    if response.status_code == 200:
        print("Slack notification sent")
    else:
        print("Slack error:", response.text)