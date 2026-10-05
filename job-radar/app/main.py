import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import get_args
from urllib.parse import urlsplit

import anthropic
import uvicorn
import yaml
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, SQLModel, col, select

from app import drafting, models, profile
from app.models import Draft, Posting, Status
from app.render import render_pdf
from app.scoring import MODEL, score
from app.settings import settings


@asynccontextmanager
async def lifespan(_):
    profile.load()  # fail at boot on a missing or invalid profile.yaml
    SQLModel.metadata.create_all(models.engine)
    models.migrate(models.engine)
    yield


app = FastAPI(lifespan=lifespan)
client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
pages = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.middleware("http")
async def no_cross_site_posts(request: Request, call_next):
    # Browsers send Origin on cross-site POSTs. Body-less POSTs (score, draft) would otherwise be
    # a free CSRF that spends API credit. /capture is exempt: the extension's origin is
    # chrome-extension://, and the endpoint checks X-Capture-Token itself.
    origin = request.headers.get("origin")
    if (request.method == "POST" and origin and request.url.path != "/capture"
            and urlsplit(origin).hostname not in ("127.0.0.1", "localhost")):
        return Response("cross-site POST refused", status_code=403)
    return await call_next(request)


class PostingIn(BaseModel):
    text: str = Field(min_length=50, max_length=50_000)


class CaptureIn(PostingIn):
    url: str = Field(max_length=2000)


class NoteIn(BaseModel):
    note: str = Field(max_length=5000)  # empty clears it


class StatusIn(BaseModel):
    status: Status


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
    return out(save(p.text))


def save(text: str) -> Posting:
    posting = Posting(text=text, **scored(text))
    with Session(models.engine) as db:
        db.add(posting)
        db.commit()
        db.refresh(posting)
        return posting


@app.post("/capture", status_code=202)
def capture(c: CaptureIn, tasks: BackgroundTasks, x_capture_token: str = Header("")) -> dict:
    """The extension's button. Answers at once: the MV3 worker may die before scoring ends."""
    if not secrets.compare_digest(x_capture_token.encode(), settings.capture_token.get_secret_value().encode()):
        raise HTTPException(401, "bad X-Capture-Token: set it in the extension's options")
    # ponytail: URL kept as the text's first line, no column; a failed score only reaches the server log.
    tasks.add_task(save, f"Source: {c.url}\n\n{c.text}")
    return {"queued": c.url}


@app.post("/postings/{posting_id}/score")
def rescore(posting_id: int) -> dict:
    with Session(models.engine) as db:
        if not (posting := db.get(Posting, posting_id)):
            raise HTTPException(404)
        note = posting.result.get("note")
        posting.sqlmodel_update(scored(posting.text))  # 502 leaves the old score untouched
        if note:
            posting.result["note"] = note  # fresh dict from scored(): no flag_modified needed
        db.add(posting)
        db.commit()
        db.refresh(posting)
        return out(posting)


@app.post("/postings/{posting_id}/missing/{n}")
def flip_severity(posting_id: int, n: int) -> dict:
    """Overrule the model: blocker <-> minor. A rescore overwrites it."""
    # ponytail: score number untouched; recompute it if overrides should move the ranking.
    with Session(models.engine) as db:
        if not (posting := db.get(Posting, posting_id)):
            raise HTTPException(404)
        missing = posting.result["missing"]
        if not 0 <= n < len(missing):
            raise HTTPException(404, f"missing item {n} not found")
        m = missing[n]
        m["severity"] = "minor" if m["severity"] == "blocker" else "blocker"
        flag_modified(posting, "result")  # JSON columns miss in-place edits
        db.add(posting)
        db.commit()
        db.refresh(posting)
        return out(posting)


@app.post("/postings/{posting_id}/note")
def save_note(posting_id: int, n: NoteIn) -> dict:
    """Your comments on the scoring; the next draft follows them."""
    # ponytail: lives in result JSON to dodge a migration; give it a column once Alembic exists.
    with Session(models.engine) as db:
        if not (posting := db.get(Posting, posting_id)):
            raise HTTPException(404)
        posting.result["note"] = n.note.strip()
        flag_modified(posting, "result")
        db.add(posting)
        db.commit()
        db.refresh(posting)
        return out(posting)


# POST, not DELETE: reuses post() and the cross-site POST check.
@app.post("/postings/{posting_id}/delete")
def delete_posting(posting_id: int) -> dict:
    """Gone for good, drafts included. Their token usage leaves the running total too."""
    with Session(models.engine) as db:
        if not (posting := db.get(Posting, posting_id)):
            raise HTTPException(404)
        for d in db.exec(select(Draft).where(Draft.posting_id == posting_id)):
            db.delete(d)
        db.delete(posting)
        db.commit()
    return {"deleted": posting_id}


@app.post("/postings/{posting_id}/status")
def set_status(posting_id: int, s: StatusIn) -> dict:
    with Session(models.engine) as db:
        if not (posting := db.get(Posting, posting_id)):
            raise HTTPException(404)
        posting.status = s.status
        db.add(posting)
        db.commit()
        db.refresh(posting)
        return out(posting)


def matches(p: Posting, q: str) -> bool:
    """Case-insensitive substring over title, company and the requirements the scorer listed."""
    reqs = [m["requirement"] for m in p.result["met"] + p.result["missing"]]
    return q.casefold() in " ".join([p.title, p.company, *reqs]).casefold()


@app.get("/postings")
def list_postings(status: Status | None = None, q: str = "") -> list[dict]:
    query = select(Posting).order_by(col(Posting.score).desc())
    if status:
        query = query.where(Posting.status == status)
    with Session(models.engine) as db:
        h = current_profile()[2]
        # ponytail: q filters in Python (requirements live in JSON); move to SQLite FTS past a few thousand rows.
        return [out(p, h) for p in db.exec(query) if matches(p, q.strip())]


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
            note = posting.result.get("note")
            text = f"{posting.text}\n\n<notes>\n{note}\n</notes>" if note else posting.text
            t, r = drafting.tailor(text, facts, client)
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


@app.get("/", response_class=HTMLResponse)
def desk(request: Request, status: Status | None = None, q: str = ""):
    return pages.TemplateResponse(request, "desk.html", {
        "postings": list_postings(status, q), "usage": usage(), "status": status, "q": q, "statuses": get_args(Status)})


@app.get("/p/{posting_id}", response_class=HTMLResponse)
def posting_page(request: Request, posting_id: int):
    p = get_posting(posting_id)
    try:
        d = get_draft(posting_id)
    except HTTPException:
        d = None
    additions = Path(profile.ADDITIONS)
    answered = {a["question"] for a in yaml.safe_load(additions.read_text(encoding="utf-8")) or []} if additions.exists() else set()
    return pages.TemplateResponse(request, "posting.html", {"p": p, "d": d, "answered": answered, "statuses": get_args(Status)})


if __name__ == "__main__":
    # Loopback only: CAPTURE_TOKEN is the sole auth. Never bind 0.0.0.0.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
