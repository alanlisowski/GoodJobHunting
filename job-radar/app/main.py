from contextlib import asynccontextmanager

import anthropic
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, SQLModel, col, select

from app import models, profile
from app.models import Posting
from app.scoring import MODEL, score
from app.settings import settings


@asynccontextmanager
async def lifespan(_):
    profile.load()  # fail at boot on a missing or invalid profile.yaml
    SQLModel.metadata.create_all(models.engine)  # ponytail: no migrations; add Alembic on the first schema change with data worth keeping
    yield


app = FastAPI(lifespan=lifespan)
client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())


class PostingIn(BaseModel):
    text: str = Field(min_length=50, max_length=50_000)


@app.get("/health")
def health():
    return {"status": "ok"}


def current_profile():
    try:
        return profile.load()  # per request: edits apply at once
    except (OSError, ValidationError, yaml.YAMLError) as e:
        raise HTTPException(500, f"profile.yaml invalid: {e}") from e


@app.get("/profile")
def get_profile() -> profile.Profile:
    return current_profile()[0]


# JSON body on purpose: FastAPI rejects non-JSON content types, so a random
# website can't fire a no-preflight form POST here and spend API credit.
@app.post("/postings", status_code=201)
def create_posting(p: PostingIn) -> Posting:
    _, text, profile_hash = current_profile()
    try:
        s, r = score(p.text, text, client)
    except (ValueError, RuntimeError, anthropic.APIError) as e:
        raise HTTPException(502, f"scoring failed: {e}") from e
    posting = Posting(
        text=p.text,
        title=s.title,
        company=s.company,
        score=s.score,
        verdict=s.verdict,
        result=s.model_dump(),
        usage=r.usage.model_dump(),
        model=MODEL,
        profile_hash=profile_hash,
    )
    with Session(models.engine) as db:
        db.add(posting)
        db.commit()
        db.refresh(posting)
    return posting


@app.get("/postings")
def list_postings() -> list[Posting]:
    with Session(models.engine) as db:
        return db.exec(select(Posting).order_by(col(Posting.score).desc())).all()


@app.get("/postings/{posting_id}")
def get_posting(posting_id: int) -> Posting:
    with Session(models.engine) as db:
        if posting := db.get(Posting, posting_id):
            return posting
    raise HTTPException(404)


if __name__ == "__main__":
    # Loopback only: CAPTURE_TOKEN is the sole auth. Never bind 0.0.0.0.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
