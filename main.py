import os
import requests
import zipfile
import io
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# you can change model here if needed
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")


@app.get("/")
async def root():
    return {"message": "CI Failure Agent running"}


@app.post("/webhook")
async def webhook(request: Request):

    print("🔥 CI FAILURE AGENT ACTIVE")

    payload = await request.json()
    print("Webhook received")

    if (
        payload.get("action") == "completed"
        and payload.get("workflow_run", {}).get("conclusion") == "failure"
    ):

        print("🚨 CI FAILURE DETECTED")

        workflow_run = payload["workflow_run"]
        repo = payload["repository"]["name"]
        owner = payload["repository"]["owner"]["login"]
        run_id = workflow_run["id"]

        logs = fetch_workflow_logs(owner, repo, run_id)

        if logs:

            log_snippet = analyze_logs(logs)

            print("===== LOG SNIPPET SENT TO LLM =====")
            print(log_snippet)
            print("===================================")

            failure_category = detect_failure_category(log_snippet)

            analysis = analyze_with_llm(log_snippet)

            message = f"""
🚨 *CI Failure Detected*

Repository: {repo}
Run ID: {run_id}

Failure Category: {failure_category}

{analysis}
"""

            send_slack_message(message)

        else:

            send_slack_message(
                f"🚨 CI Failed in {repo}\n\nUnable to download CI logs."
            )

    return {"status": "received"}


# ------------------------------------------------------------
# DOWNLOAD GITHUB ACTION LOGS
# ------------------------------------------------------------

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

        zip_bytes = io.BytesIO(response.content)

        with zipfile.ZipFile(zip_bytes) as z:

            combined_logs = ""

            for file_name in z.namelist():

                with z.open(file_name) as f:

                    combined_logs += f.read().decode(
                        "utf-8", errors="ignore"
                    )

        print("Logs extracted successfully")

        return combined_logs[-8000:]

    except Exception as e:

        print("Error extracting logs:", e)
        return None


# ------------------------------------------------------------
# FIND FAILURE SNIPPET
# ------------------------------------------------------------

def analyze_logs(log_text):

    lines = log_text.splitlines()

    failure_indicators = [
        "Traceback",
        "AssertionError",
        "ModuleNotFoundError",
        "SyntaxError",
        "FAILED",
        "ERROR",
        "Exception"
    ]

    for i in range(len(lines) - 1, -1, -1):

        for keyword in failure_indicators:

            if keyword in lines[i]:

                start = max(i - 15, 0)
                end = min(i + 25, len(lines))

                return "\n".join(lines[start:end])

    return "\n".join(lines[-300:])


# ------------------------------------------------------------
# SIMPLE FAILURE CATEGORY CLASSIFIER
# ------------------------------------------------------------

def detect_failure_category(log):

    if "AssertionError" in log:
        return "Test Failure"

    if "SyntaxError" in log:
        return "Syntax Error"

    if "ModuleNotFoundError" in log:
        return "Missing Dependency"

    if "ImportError" in log:
        return "Import Error"

    if "fatal:" in log or "error 500" in log:
        return "Infrastructure Error"

    return "Unknown"


# ------------------------------------------------------------
# LLM ANALYSIS
# ------------------------------------------------------------

def analyze_with_llm(log_snippet):

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
You are an expert CI/CD debugging assistant.

Analyze the following CI failure log.

Your job:
1. Identify the root cause
2. Identify the exact failing line
3. Suggest a precise fix

Respond strictly in this format:

Root Cause:
<short technical explanation>

Failing Line:
<line causing failure>

Fix:
<exact fix needed>

Log:
{log_snippet}
"""

    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "CI/CD debugging expert"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
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


# ------------------------------------------------------------
# SEND SLACK MESSAGE
# ------------------------------------------------------------

def send_slack_message(message):

    data = {"text": message}

    response = requests.post(SLACK_WEBHOOK_URL, json=data)

    if response.status_code == 200:

        print("Slack notification sent")

    else:

        print("Slack error:", response.text)