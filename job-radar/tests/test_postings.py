from types import SimpleNamespace

from anthropic.types import Usage
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import main, models
from app.scoring import Score

TEXT = "Junior Python Developer at Acme. FastAPI, SQL, remote. " * 2


def test_paste_score_list(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(models, "engine", engine)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "profile.yaml").write_text("name: Test", encoding="utf-8")
    scores = iter([40, 90])

    def fake_score(posting, profile, client):
        s = Score(title="Dev", company="Acme", score=next(scores),
                  met=[], missing=[], dealbreakers_hit=[], verdict="ok")
        return s, SimpleNamespace(usage=Usage(input_tokens=10, output_tokens=5))

    monkeypatch.setattr(main, "score", fake_score)
    c = TestClient(main.app)

    assert c.post("/postings", json={"text": TEXT}).status_code == 201
    assert c.post("/postings", json={"text": TEXT}).status_code == 201
    assert [p["score"] for p in c.get("/postings").json()] == [90, 40]
    assert c.get("/postings/1").json()["company"] == "Acme"
    assert c.get("/postings/99").status_code == 404
    assert c.post("/postings", json={"text": "too short"}).status_code == 422
    # A cross-site form POST (no CORS preflight) must not reach the paid model call.
    r = c.post("/postings", content=f'{{"text": "{TEXT}"}}',
               headers={"content-type": "text/plain"})
    assert r.status_code == 422
