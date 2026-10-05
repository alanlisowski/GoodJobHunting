from app import main
from app.scoring import Score
from tests.conftest import RAW

BODY = {"url": "https://justjoin.it/job-offer/acme-python", "text": "Junior Python Developer at Acme. FastAPI, SQL. " * 3}
EXT = {"origin": "chrome-extension://abcdefghijklmnop"}


def test_capture_needs_the_token_then_scores_in_the_background(api, monkeypatch):
    seen = []
    monkeypatch.setattr(main, "score", lambda text, *a: (seen.append(text), (Score(
        title="Python Dev", company="Acme", score=70, met=[], missing=[], dealbreakers_hit=[], verdict="ok"), RAW))[1])
    token = main.settings.capture_token.get_secret_value()

    assert api.post("/capture", json=BODY, headers=EXT).status_code == 401
    assert api.post("/capture", json=BODY, headers={**EXT, "x-capture-token": token + "x"}).status_code == 401
    assert seen == []  # no paid call without the token

    assert api.post("/capture", json=BODY, headers={**EXT, "x-capture-token": token}).status_code == 202
    assert seen[0].startswith("Source: https://justjoin.it/job-offer/acme-python\n\n")
    assert api.get("/postings").json()[0]["title"] == "Python Dev"
    # Everything else still refuses that origin.
    assert api.post("/postings", json={"text": BODY["text"]}, headers=EXT).status_code == 403
