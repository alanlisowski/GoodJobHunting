"""What do you want to do? Job titles that fit the facts, and what to type into the boards."""

import re

import anthropic
from pydantic import BaseModel, Field

from app.scoring import MODEL, ask

RULES = """You advise a job hunter which job titles to search for, given their facts:
profile.yaml (constraints, dealbreakers), cv_*.yaml (their real CVs) and profile_additions.yaml.
Return 4-6 titles, best fit first. Each title's "why" must cite specific facts (skills, projects,
experience) and list them in "evidence". A title with no evidence is not allowed: drop it instead.
"gaps" are what the candidate would still have to close for that title.
"search_terms" are short strings to type into justjoin.it or pracuj.pl search; give Polish and
English variants where the boards use both (e.g. "programista python", "python developer").
"look_for" and "skip" must apply the dealbreakers and work constraints (modes, commute, salary
floor, relocation) from profile.yaml.
If a <desk> table is given, it shows how the candidate's captured postings actually scored per
title family: let it shift your advice."""


class Title(BaseModel):
    title_en: str
    title_pl: str
    fit: int = Field(ge=0, le=100)
    why: str
    evidence: list[str] = Field(min_length=1)  # facts it rests on; no evidence, no title
    gaps: list[str]
    search_terms: list[str]


class Advice(BaseModel):
    titles: list[Title] = Field(min_length=4, max_length=6)
    look_for: list[str]
    skip: list[str]


# First match wins, so the broad families (frontend, python/backend) go last.
# ponytail: keyword families; a title like "Software Engineer" lands in other until it earns a keyword.
FAMILIES = {
    "fullstack": r"full ?stack",
    "qa/test": r"qa|test\w*|sdet|quality",
    "devops": r"devops|sre|platform|cloud|infrastructure",
    "data": r"data|danych|ml|machine learning|ai|analyst|analityk",
    "java/jvm": r"java|kotlin|scala|jvm|spring",
    "python/backend": r"python|django|fastapi|flask|back ?end",
    "frontend": r"front ?end|react|angular|vue|javascript|typescript",
}


def family(title: str) -> str:
    t = re.sub(r"[\W_]+", " ", title.casefold())  # "Full-Stack" -> "full stack"; keeps Polish letters
    return next((f for f, kw in FAMILIES.items() if re.search(rf"\b(?:{kw})\b", t)), "other")


def desk(postings: list[tuple[str, int]]) -> list[dict]:
    """(title, score) pairs -> count and average fit per family, best average first."""
    fams: dict[str, list[int]] = {}
    for title, score in postings:
        fams.setdefault(family(title), []).append(score)
    rows = [{"family": f, "count": len(s), "avg": round(sum(s) / len(s))} for f, s in fams.items()]
    return sorted(rows, key=lambda r: -r["avg"])


def advise(facts: str, table: list[dict], client: anthropic.Anthropic) -> tuple[Advice, object]:
    lines = "\n".join(f"{r['family']}: {r['count']} postings, average fit {r['avg']}" for r in table)
    return ask(client, MODEL, RULES, facts, lines or "No scored postings yet.", Advice, tag="desk")

