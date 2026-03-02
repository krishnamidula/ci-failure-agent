from fastapi import FastAPI, Request

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Server running"}


@app.post("/webhook")
async def webhook(request: Request):
    # read JSON payload
    payload = await request.json()
    print("Received payload:", payload)
    return {"status": "received"}
