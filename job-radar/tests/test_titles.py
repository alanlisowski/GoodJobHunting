from types import SimpleNamespace

import pytest
from anthropic.types import Usage

from app import main
from app.scoring import Score
from app.titles import Advice, advise, desk, family
from tests.conftest import RAW

AIM = {"title_en": "Python Developer", "title_pl": "Programista Python",
       "why": "Built job-radar on FastAPI.", "evidence": ["job-radar (FastAPI)"]}
NOT = {"title_en": "Senior Java Developer", "why_not": "No Java on record; a Spring project would change that."}
GOOD = {"aim_for": [AIM, {**AIM, "title_en": "Backend Developer"}, {**AIM, "title_en": "Junior Data Engineer"}],
        "not_these": [NOT, NOT], "search_terms": ["python developer", "programista python", "backend", "fastapi"]}
USAGE = SimpleNamespace(usage=Usage(input_tokens=1, output_tokens=1), model_dump_json=lambda: "{}")


class FakeClient:
    """Mimics messages.parse: the SDK validates against the schema and raises on a bad shape."""

    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), 0
        self.messages = self

    def parse(self, output_format, **kw):
        self.calls += 1
        return SimpleNamespace(parsed_output=output_format.model_validate(self.outputs.pop(0)),
                               stop_reason="end_turn", content="", usage=Usage(input_tokens=7, output_tokens=3),
                               model_dump_json=lambda: "{}")


@pytest.mark.parametrize("bad", [
    {**GOOD, "aim_for": GOOD["aim_for"][:2]},  # exactly 3
    {**GOOD, "not_these": [NOT]},  # 2-3
    {**GOOD, "not_these": [NOT] * 4},
    {**GOOD, "search_terms": ["a", "b", "c"]},  # 4-8
    {**GOOD, "search_terms": ["a"] * 9},
    {**GOOD, "aim_for": [{**AIM, "evidence": []}] * 3},  # no evidence, no title
])
def test_schema_rejects(bad):
    with pytest.raises(ValueError):
        Advice.model_validate(bad)


def test_bad_shape_retried_once():
    a, _ = advise("facts", [], FakeClient({"aim_for": []}, GOOD))
    assert a.aim_for[0].title_pl == "Programista Python"
    with pytest.raises(ValueError):
        advise("facts", [], FakeClient({"aim_for": []}, {"search_terms": []}))


def test_only_post_calls_the_model(api, monkeypatch):
    fake = FakeClient(GOOD, GOOD)
    monkeypatch.setattr(main, "client", fake)
    assert "Not sure what to aim for? Find out →" in api.get("/").text
    page = api.get("/titles").text
    assert "Think it through" in page and "Not these" not in page
    assert fake.calls == 0

    assert api.post("/titles/rethink").status_code == 200
    assert fake.calls == 1
    desk_page = api.get("/").text
    assert "Python Developer · Backend Developer · Junior Data Engineer" in desk_page and "Why these? →" in desk_page
    page = api.get("/titles").text
    assert "Not these, for now" in page and "programista python" in page and "profile v1" in page
    assert fake.calls == 1  # stored advice is reused

    with open("profile.yaml", "a", encoding="utf-8") as f:
        f.write("\n# edited\n")
    assert "stale" in api.get("/titles").text
    assert fake.calls == 1  # a changed profile shows stale; only Rethink calls again
    api.post("/titles/rethink")
    page = api.get("/titles").text
    assert fake.calls == 2 and "stale" not in page and "profile v2" in page
    assert api.get("/usage").json()["input_tokens"] == 14


def test_families_reach_the_prompt_not_the_ui(api, monkeypatch):
    monkeypatch.setattr(main, "score", lambda *a: (Score(
        title="Python Dev", company="Acme", score=70, met=[], missing=[], dealbreakers_hit=[], verdict="ok"), RAW))
    for _ in range(3):
        api.post("/postings", json={"text": "Junior Python Developer at Acme. FastAPI, SQL, remote. " * 2})
    seen = []
    monkeypatch.setattr(main.titles, "advise", lambda facts, table, client: (
        seen.append(table), (Advice.model_validate(GOOD), USAGE))[1])
    api.post("/titles/rethink")
    assert seen == [[{"family": "python/backend", "count": 3, "avg": 70}]]
    for page in (api.get("/").text, api.get("/titles").text):
        assert "From your desk" not in page and "python/backend" not in page
    assert "Acme" not in api.get("/titles").text  # no individual postings on /titles


def test_model_failure_stores_nothing(api):
    assert api.post("/titles/rethink").status_code == 502  # conftest's client always fails
    assert "Think it through" in api.get("/titles").text


def test_families():
    assert family("Senior Python Developer") == "python/backend"
    assert family("Full-Stack Engineer (React/Node)") == "fullstack"
    assert family("JavaScript Developer") == "frontend"  # not java
    assert family("Tester automatyczny") == "qa/test"
    assert family("Inżynier danych") == "data"
    assert family("Office Manager") == "other"
    assert family("Software Engineer", ["3+ years of Python", "FastAPI"]) == "python/backend"
    assert family("Software Engineer", ["Kotlin", "Python"]) == "java/jvm"  # FAMILIES order, not tech order
    assert family("Software Engineer", ["Communication", "Agile"]) == "other"
    assert family("Software Engineer") == "other"
    assert desk([("Python Dev", [], 80), ("Software Engineer", ["Django"], 60), ("Java Dev", [], 90)]) == [
        {"family": "java/jvm", "count": 1, "avg": 90}, {"family": "python/backend", "count": 2, "avg": 70}]
