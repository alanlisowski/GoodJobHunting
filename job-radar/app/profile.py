"""The candidate's facts: what every model call is allowed to believe.

profile.yaml         constraints a CV doesn't carry (validated below)
cv_<lang>.yaml       the real CVs, one per language (shape: templates/cv.html)
profile_additions.yaml  answers to gap questions (appended by the app)
"""

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

ADDITIONS = "profile_additions.yaml"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo'd key fails instead of vanishing


class Work(Strict):
    modes: list[Literal["remote", "hybrid", "onsite"]]
    max_commute_min: int
    relocation: bool
    salary_floor_pln: int


class Profile(Strict):
    city: str  # where commutes start from
    work: Work
    dealbreakers: list[str]


def load(path: str = "profile.yaml") -> tuple[Profile, str, str]:
    """Validated profile, all facts as one text (what the model sees), sha256 of that text."""
    root = Path(path).parent
    text = Path(path).read_text(encoding="utf-8")
    p = Profile.model_validate(yaml.safe_load(text))
    cvs = sorted(root.glob("cv_*.yaml"))
    if not cvs:
        raise FileNotFoundError(f"no cv_<lang>.yaml next to {path}: the CVs are the facts")
    files = [Path(path), *cvs, *[f for f in [root / ADDITIONS] if f.exists()]]
    facts = ""
    for f in files:
        body = f.read_text(encoding="utf-8")
        yaml.safe_load(body)  # fail loudly on a broken CV or additions file
        facts += f"<file name=\"{f.name}\">\n{body}\n</file>\n"
    return p, facts, hashlib.sha256(facts.encode()).hexdigest()


def base_cv(lang: str, root: str = ".") -> dict:
    return yaml.safe_load((Path(root) / f"cv_{lang}.yaml").read_text(encoding="utf-8"))
