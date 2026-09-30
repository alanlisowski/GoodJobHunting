from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app import profile

EXAMPLE = Path(__file__).parents[1] / "profile.example.yaml"


def test_facts_are_profile_cvs_and_answers(api):
    p, facts, h = profile.load()
    assert p.work.relocation is False and 'name="cv_en.yaml"' in facts
    Path(profile.ADDITIONS).write_text('- {question: "Docker?", answer: "yes"}\n', encoding="utf-8")
    _, facts2, h2 = profile.load()
    assert "Docker?" in facts2 and h2 != h  # an answer makes old scores stale

    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for broken in ({k: v for k, v in data.items() if k != "work"},  # missing field
                   {**data, "skils": []}):  # typo'd key
        Path("profile.yaml").write_text(yaml.safe_dump(broken), encoding="utf-8")
        with pytest.raises(ValidationError):
            profile.load()
    assert api.get("/profile").status_code == 500  # still broken

    Path("profile.yaml").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    Path("cv_en.yaml").unlink()
    with pytest.raises(FileNotFoundError):
        profile.load()
