import shutil
from pathlib import Path
from types import SimpleNamespace

from anthropic.types import Usage
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import main, models
from app.scoring import Score

EXAMPLE = Path(__file__).parents[1] / "profile.example.yaml"
TEXT = "Junior Python Developer at Acme. FastAPI, SQL, remote. " * 2


def test_paste_score_list(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(models, "engine", engine)
    monkeypatch.chdir(tmp_path)
    shutil.copy(EXAMPLE, tmp_path / "profile.yaml")
    scores = iter([40, 90, 70])

    def fake_score(posting, profile, client):
        s = Score(title="Dev", company="Acme", score=next(scores),
                  met=[], missing=[], dealbreakers_hit=[], verdict="ok")
        return s, SimpleNamespace(usage=Usage(input_tokens=10, output_tokens=5),
                                  model_dump_json=lambda: '{"raw": 1}')

    monkeypatch.setattr(main, "score", fake_score)
    c = TestClient(main.app)

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
