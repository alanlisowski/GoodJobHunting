import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo'd key fails instead of vanishing


class Work(Strict):
    modes: list[Literal["remote", "hybrid", "onsite"]]
    max_commute_min: int
    relocation: bool
    salary_floor_pln: int


class Skill(Strict):
    name: str
    level: int = Field(ge=1, le=5)
    years: float
    evidence: str


class Project(Strict):
    name: str
    stack: list[str]
    built: str
    links: list[str] = []


class Profile(Strict):
    name: str
    city: str
    languages: dict[str, Literal["A1", "A2", "B1", "B2", "C1", "C2", "native"]]
    work: Work
    skills: list[Skill]
    projects: list[Project]
    # ponytail: free-form until drafting (milestone 5) needs to cite them; type them then.
    experience: list[dict]
    education: list[dict]
    certificates: list[str]
    dealbreakers: list[str]


def load(path: str = "profile.yaml") -> tuple[Profile, str, str]:
    """Validated profile, raw text (what the model sees), sha256 of that text."""
    text = Path(path).read_text(encoding="utf-8")
    return Profile.model_validate(yaml.safe_load(text)), text, hashlib.sha256(text.encode()).hexdigest()
