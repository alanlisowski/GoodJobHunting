import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    # Loopback only: CAPTURE_TOKEN is the sole auth. Never bind 0.0.0.0.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
