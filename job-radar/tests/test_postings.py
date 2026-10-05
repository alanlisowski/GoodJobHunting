from app import main
from app.scoring import Score
from tests.conftest import RAW

TEXT = "Junior Python Developer at Acme. FastAPI, SQL, remote. " * 2


def test_paste_score_list(api, monkeypatch):
    scores = iter([40, 90, 70])

    def fake_score(posting, facts, client):
        return Score(title="Dev", company="Acme", score=next(scores),
                     met=[], missing=[], dealbreakers_hit=[], verdict="ok"), RAW

    monkeypatch.setattr(main, "score", fake_score)
    c = api

    assert c.post("/postings", json={"text": TEXT}).status_code == 201
    assert c.post("/postings", json={"text": TEXT}).status_code == 201
    assert [p["score"] for p in c.get("/postings").json()] == [90, 40]
    assert c.get("/postings/1").json()["company"] == "Acme"
    assert c.get("/postings/99").status_code == 404
    assert c.post("/postings", json={"text": "too short"}).status_code == 422
    assert c.get("/usage").json()["output_tokens"] == 10
    assert c.get("/postings/1").json()["raw"] == '{"raw": 1}'

    # Profile edit -> old scores are stale until rescored.
    assert not any(p["stale"] for p in c.get("/postings").json())
    with open("profile.yaml", "a", encoding="utf-8") as f:
        f.write("# edited\n")
    assert all(p["stale"] for p in c.get("/postings").json())
    r = c.post("/postings/1/score").json()
    assert (r["score"], r["stale"]) == (70, False)
    assert c.get("/postings/2").json()["stale"]
    assert c.post("/postings/99/score").status_code == 404
    # A cross-site form POST (no CORS preflight) must not reach the paid model call.
    r = c.post("/postings", content=f'{{"text": "{TEXT}"}}',
               headers={"content-type": "text/plain"})
    assert r.status_code == 422


def test_failed_rescore_keeps_the_old_score(api, monkeypatch):
    monkeypatch.setattr(main, "score", lambda *a: (Score(
        title="Dev", company="Acme", score=55, met=[], missing=[], dealbreakers_hit=[], verdict="ok"), RAW))
    api.post("/postings", json={"text": TEXT})

    def boom(*a):
        raise ValueError("unparseable Score after retry")

    monkeypatch.setattr(main, "score", boom)
    assert api.post("/postings/1/score").status_code == 502
    assert api.get("/postings/1").json()["score"] == 55
