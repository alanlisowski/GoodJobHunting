from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main, profile

EXAMPLE = Path(__file__).parents[1] / "profile.example.yaml"


def test_profile_validates_and_serves(tmp_path, monkeypatch):
    p, _, h = profile.load(str(EXAMPLE))
    assert p.work.relocation is False and len(h) == 64

    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for broken in ({k: v for k, v in data.items() if k != "work"},  # missing field
                   {**data, "skils": []},  # typo'd key
                   {**data, "languages": {"english": "fluent"}}):  # not CEFR
        (tmp_path / "profile.yaml").write_text(yaml.safe_dump(broken), encoding="utf-8")
        with pytest.raises(ValidationError):
            profile.load(str(tmp_path / "profile.yaml"))

    monkeypatch.chdir(tmp_path)
    c = TestClient(main.app)
    assert c.get("/profile").status_code == 500  # still broken from above
    (tmp_path / "profile.yaml").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    assert c.get("/profile").json()["city"] == "Kraków"
