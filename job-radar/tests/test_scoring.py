from types import SimpleNamespace

import pytest

from app.scoring import Score, score
from scripts.eval_ranking import spearman

GOOD = Score(title="Dev", company="Acme", score=80, met=[], missing=[], dealbreakers_hit=[], verdict="ok")


class FakeClient:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.messages = self

    def parse(self, **kw):
        return SimpleNamespace(parsed_output=self.outputs.pop(0), stop_reason="end_turn", content="")


def test_score_retries_once_then_succeeds():
    s, _ = score("posting", "profile", FakeClient(None, GOOD))
    assert s.score == 80


def test_score_gives_up_after_retry():
    with pytest.raises(ValueError):
        score("posting", "profile", FakeClient(None, None))


def test_spearman():
    assert spearman(list("abc"), list("abc")) == 1
    assert spearman(list("abc"), list("cba")) == -1


def test_refusal_is_an_error_not_a_score():
    c = FakeClient()
    c.parse = lambda **kw: SimpleNamespace(parsed_output=None, stop_reason="refusal", stop_details="nope", content="")
    with pytest.raises(RuntimeError, match="refused"):
        score("posting", "profile", c)
