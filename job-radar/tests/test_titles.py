from types import SimpleNamespace

import pytest
from anthropic.types import Usage

from app import main
from app.titles import Advice, advise, desk, family

TITLE = {"title_en": "Python Developer", "title_pl": "Programista Python", "fit": 82,
         "why": "FastAPI project", "evidence": ["job-radar (FastAPI)"], "gaps": ["Kubernetes"],
         "search_terms": ["python developer", "programista python"]}
GOOD = {"titles": [TITLE] * 4, "look_for": ["remote"], "skip": ["onsite Warsaw"]}


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


def test_bad_shape_retried_once():
    a, _ = advise("facts", [], FakeClient({"titles": []}, GOOD))
    assert a.titles[0].title_pl == "Programista Python"
    with pytest.raises(ValueError):
        advise("facts", [], FakeClient({"titles": []}, {"look_for": []}))


def test_title_without_evidence_rejected():
    with pytest.raises(ValueError):
        Advice.model_validate({**GOOD, "titles": [{**TITLE, "evidence": []}] * 4})


def test_cached_per_profile_then_stale(api, monkeypatch):
    fake = FakeClient(GOOD, GOOD)
    monkeypatch.setattr(main, "client", fake)
    assert "Programista Python" in api.get("/titles").text
    assert "Programista Python" in api.get("/").text
    assert fake.calls == 1  # same profile_hash: no second call

    with open("profile.yaml", "a", encoding="utf-8") as f:
        f.write("\n# edited\n")
    assert "stale" in api.get("/titles?partial=1").text
    assert fake.calls == 1  # a changed profile shows stale; only Rethink calls again
    api.post("/titles/rethink")
    assert fake.calls == 2 and "stale" not in api.get("/titles").text
    assert api.get("/usage").json()["input_tokens"] == 14


def test_model_failure_stores_nothing(api):
    assert "Couldn't get title advice" in api.get("/titles").text  # conftest's client always fails
    assert api.post("/titles/rethink").status_code == 502


def test_families():
    assert family("Senior Python Developer") == "python/backend"
    assert family("Full-Stack Engineer (React/Node)") == "fullstack"
    assert family("JavaScript Developer") == "frontend"  # not java
    assert family("Tester automatyczny") == "qa/test"
    assert family("Inżynier danych") == "data"
    assert family("Office Manager") == "other"
    assert desk([("Python Dev", 80), ("Django Dev", 60), ("Java Dev", 90)]) == [
        {"family": "java/jvm", "count": 1, "avg": 90}, {"family": "python/backend", "count": 2, "avg": 70}]
