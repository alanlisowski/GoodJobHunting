from contextlib import asynccontextmanager
from datetime import date

import anthropic
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, SQLModel, col, select

from app import drafting, models, profile
from app.models import Draft, Posting
from app.render import render_pdf
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


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health():
    return {"status": "ok"}


def current_profile():
    try:
        return profile.load()  # per request: edits apply at once
    except (OSError, ValidationError, yaml.YAMLError) as e:
        raise HTTPException(500, f"profile.yaml invalid: {e}") from e


def scored(text: str) -> dict:
    """Posting fields from a fresh score against the current profile."""
    _, profile_text, profile_hash = current_profile()
    try:
        s, r = score(text, profile_text, client)
    except (ValueError, RuntimeError, anthropic.APIError) as e:
        raise HTTPException(502, f"scoring failed: {e}") from e
    return {
        "title": s.title, "company": s.company, "score": s.score, "verdict": s.verdict,
        "result": s.model_dump(), "usage": r.usage.model_dump(), "raw": r.model_dump_json(),
        "model": MODEL, "profile_hash": profile_hash,
    }


def out(p: Posting, profile_hash: str | None = None) -> dict:
    """Posting plus `stale`: scored against a profile that has since changed."""
    profile_hash = profile_hash or current_profile()[2]
    return {**p.model_dump(), "stale": p.profile_hash != profile_hash}


@app.get("/profile")
def get_profile() -> profile.Profile:
    return current_profile()[0]


# JSON body on purpose: FastAPI rejects non-JSON content types, so a random
# website can't fire a no-preflight form POST here and spend API credit.
@app.post("/postings", status_code=201)
def create_posting(p: PostingIn) -> dict:
    posting = Posting(text=p.text, **scored(p.text))
    with Session(models.engine) as db:
        db.add(posting)
        db.commit()
        db.refresh(posting)
        return out(posting)


@app.post("/postings/{posting_id}/score")
def rescore(posting_id: int) -> dict:
    with Session(models.engine) as db:
        if not (posting := db.get(Posting, posting_id)):
            raise HTTPException(404)
        posting.sqlmodel_update(scored(posting.text))  # 502 leaves the old score untouched
        db.add(posting)
        db.commit()
        db.refresh(posting)
        return out(posting)


@app.get("/postings")
def list_postings() -> list[dict]:
    with Session(models.engine) as db:
        h = current_profile()[2]
        return [out(p, h) for p in db.exec(select(Posting).order_by(col(Posting.score).desc()))]


@app.get("/usage")
def usage() -> dict:
    # ponytail: sums in Python over every row; fine for one user's few hundred postings.
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    with Session(models.engine) as db:
        rows = [*db.exec(select(Posting.usage)), *db.exec(select(Draft.usage))]
    return {k: sum(u.get(k) or 0 for u in rows) for k in keys}


@app.get("/postings/{posting_id}")
def get_posting(posting_id: int) -> dict:
    with Session(models.engine) as db:
        if posting := db.get(Posting, posting_id):
            return out(posting)
    raise HTTPException(404)


def latest_draft(db: Session, posting_id: int) -> Draft:
    d = db.exec(select(Draft).where(Draft.posting_id == posting_id).order_by(col(Draft.id).desc())).first()
    if not d:
        raise HTTPException(404, "no draft yet: POST /postings/{id}/draft")
    return d


def draft_out(d: Draft) -> dict:
    return {**d.model_dump(exclude={"raw"}), "stale": d.profile_hash != current_profile()[2]}


@app.post("/postings/{posting_id}/draft", status_code=201)
def create_draft(posting_id: int) -> dict:
    """(Re)draft the CV and letter. Costs a strong-model call: answer the open gaps first."""
    _, facts, profile_hash = current_profile()
    with Session(models.engine) as db:
        if not (posting := db.get(Posting, posting_id)):
            raise HTTPException(404)
        try:
            t, r = drafting.tailor(posting.text, facts, client)
        except (ValueError, RuntimeError, anthropic.APIError) as e:
            raise HTTPException(502, f"drafting failed: {e}") from e
        d = Draft(posting_id=posting_id, data=t.model_dump(), raw=r.model_dump_json(),
                  usage=r.usage.model_dump(), model=drafting.MODEL, profile_hash=profile_hash)
        db.add(d)
        db.commit()
        db.refresh(d)
        return draft_out(d)


@app.get("/postings/{posting_id}/draft")
def get_draft(posting_id: int) -> dict:
    with Session(models.engine) as db:
        return draft_out(latest_draft(db, posting_id))


@app.post("/postings/{posting_id}/gaps/{n}")
def answer_gap(posting_id: int, n: int, a: AnswerIn) -> dict:
    """Your answer becomes a fact (profile_additions.yaml). Redraft to use it."""
    with Session(models.engine) as db:
        gaps = latest_draft(db, posting_id).data["gaps"]
    if not 0 <= n < len(gaps):
        raise HTTPException(404, f"gap {n} not found: this draft has {len(gaps)}")
    with open(profile.ADDITIONS, "a", encoding="utf-8") as f:
        f.write(yaml.safe_dump([{**gaps[n], "answer": a.answer}], allow_unicode=True, sort_keys=False))
    return {"saved": gaps[n]["question"]}


def pdf(posting_id: int, template: str) -> Response:
    p, _, _ = current_profile()
    with Session(models.engine) as db:
        t = latest_draft(db, posting_id).data
        company = db.get(Posting, posting_id).company
    try:
        base = profile.base_cv(t["lang"])
    except OSError as e:
        raise HTTPException(500, f"no base CV for this language: {e}") from e
    data = drafting.cv_data(t, base)
    if template == "letter.html":
        data |= {"letter": t["letter"], "company": company, "city": p.city,
                 "date": date.today().strftime("%d.%m.%Y")}  # noqa: DTZ011 - the letter wants the local date
    return Response(render_pdf(data, template), media_type="application/pdf")


@app.get("/postings/{posting_id}/cv.pdf")
def cv_pdf(posting_id: int) -> Response:
    return pdf(posting_id, "cv.html")


@app.get("/postings/{posting_id}/letter.pdf")
def letter_pdf(posting_id: int) -> Response:
    return pdf(posting_id, "letter.html")


if __name__ == "__main__":
    # Loopback only: CAPTURE_TOKEN is the sole auth. Never bind 0.0.0.0.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
