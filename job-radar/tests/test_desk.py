from app import main
from app.scoring import Met, Missing, Score
from tests.conftest import RAW

TEXT = "Junior Python Developer at Acme. FastAPI, SQL, remote. " * 2


def test_desk_pages(api, monkeypatch):
    monkeypatch.setattr(main, "score", lambda *a: (Score(
        title="Python Dev", company="Acme", score=77, met=[Met(requirement="FastAPI", evidence_from_profile="job-radar")],
        missing=[], dealbreakers_hit=[], verdict="Apply."), RAW))
    assert "Nothing yet" in api.get("/").text
    api.post("/postings", json={"text": TEXT})

    assert "Python Dev" in api.get("/").text
    page = api.get("/p/1").text
    assert "FastAPI" in page and "Draft CV and letter" in page
    assert api.get("/p/99").status_code == 404

    # A page on another site must not trigger paid calls; our own pages and non-browser clients can.
    assert api.post("/postings/1/score", headers={"origin": "https://evil.example"}).status_code == 403
    assert api.post("/postings/1/score", headers={"origin": "null"}).status_code == 403
    assert api.post("/postings/1/score", headers={"origin": "http://127.0.0.1:8000"}).status_code == 200


def test_flip_blocker(api, monkeypatch):
    monkeypatch.setattr(main, "score", lambda *a: (Score(
        title="Python Dev", company="Acme", score=40, met=[],
        missing=[Missing(requirement="5y Java", severity="blocker")], dealbreakers_hit=[], verdict="Skip."), RAW))
    api.post("/postings", json={"text": TEXT})
    assert "Not a blocker" in api.get("/p/1").text

    assert api.post("/postings/1/missing/0").json()["result"]["missing"][0]["severity"] == "minor"
    assert api.get("/postings/1").json()["result"]["missing"][0]["severity"] == "minor"  # persisted
    assert api.post("/postings/1/missing/0").json()["result"]["missing"][0]["severity"] == "blocker"
    assert api.post("/postings/1/missing/5").status_code == 404


def test_note_reaches_draft_and_survives_rescore(api, monkeypatch):
    monkeypatch.setattr(main, "score", lambda *a: (Score(
        title="Python Dev", company="Acme", score=40, met=[], missing=[], dealbreakers_hit=[], verdict="Skip."), RAW))
    api.post("/postings", json={"text": TEXT})
    assert api.post("/postings/1/note", json={"note": " I used Java at uni. "}).json()["result"]["note"] == "I used Java at uni."
    assert "I used Java at uni." in api.get("/p/1").text

    api.post("/postings/1/score")
    assert api.get("/postings/1").json()["result"]["note"] == "I used Java at uni."

    seen = []
    monkeypatch.setattr(main.drafting, "tailor", lambda text, *a: seen.append(text) or (_ for _ in ()).throw(ValueError("stop")))
    api.post("/postings/1/draft")
    assert seen[0].endswith("<notes>\nI used Java at uni.\n</notes>")
