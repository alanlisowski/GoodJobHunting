import io
from pathlib import Path

from pypdf import PdfReader

from app import drafting, main
from app.drafting import Entry, Gap, Skill, Tailored
from app.scoring import Score
from tests.conftest import RAW

TEXT = "Python Developer at Acme. FastAPI, Kubernetes, remote. " * 2


def test_gap_loop(api, monkeypatch):
    monkeypatch.setattr(main, "score", lambda *a: (Score(
        title="Dev", company="Acme", score=80, met=[], missing=[], dealbreakers_hit=[], verdict="ok"), RAW))
    seen = []

    def fake_tailor(posting, facts, client):
        seen.append(facts)
        answered = "Kubernetes" in facts
        return Tailored(
            lang="en", headline="Python Developer", about="Builds APIs in FastAPI.",
            skills=[Skill(label="Back-end", value="FastAPI" + (", Kubernetes" if answered else ""))],
            projects=[Entry(title="job-radar", right="github.com/x", text="Scores postings.", bullets=[])],
            experience=[], letter=["I build APIs.", "Acme fits."],
            gaps=[] if answered else [Gap(requirement="Kubernetes", question="Have you run Kubernetes?")],
        ), RAW

    monkeypatch.setattr(drafting, "tailor", fake_tailor)
    api.post("/postings", json={"text": TEXT})
    assert api.post("/postings/1/gaps/0", json={"answer": "x"}).status_code == 404  # no draft yet

    d = api.post("/postings/1/draft").json()
    assert d["data"]["gaps"][0]["requirement"] == "Kubernetes" and not d["stale"]
    assert api.post("/postings/1/gaps/5", json={"answer": "x"}).status_code == 404

    # The answer becomes a fact: the draft goes stale, the next draft sees it.
    assert api.post("/postings/1/gaps/0", json={"answer": "Yes, k3s at home for a year"}).status_code == 200
    assert "k3s at home" in Path("profile_additions.yaml").read_text(encoding="utf-8")
    assert api.get("/postings/1/draft").json()["stale"]
    d = api.post("/postings/1/draft").json()
    assert d["data"]["gaps"] == [] and "k3s at home" in seen[-1]
    assert api.get("/usage").json()["output_tokens"] == 15  # 1 score + 2 drafts

    cv = PdfReader(io.BytesIO(api.get("/postings/1/cv.pdf").content))
    text = cv.pages[0].extract_text()
    assert len(cv.pages) == 1 and "FastAPI, Kubernetes" in text and "BSc Computer Science" in text
    letter = PdfReader(io.BytesIO(api.get("/postings/1/letter.pdf").content)).pages[0].extract_text()
    assert "Acme fits." in letter and "Dear Hiring Team" in letter
