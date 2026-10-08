"""What do you want to do? Titles to aim for, titles to skip for now, and what to type into the boards."""

import re

import anthropic
from pydantic import BaseModel, Field

from app.scoring import MODEL, ask

RULES = """You advise a job hunter which job titles to aim for, given their facts:
profile.yaml (constraints, dealbreakers), cv_*.yaml (their real CVs) and profile_additions.yaml.
"aim_for": exactly 3 titles, best fit first. "why" is ONE sentence (max ~25 words) citing specific
facts (skills, projects, experience); list those facts in "evidence". No evidence, no title.
"not_these": 2-3 titles people with this background often apply for but shouldn't yet. "why_not" is
ONE sentence (max ~25 words): the missing skill, dealbreaker or work constraint (modes, commute,
salary floor, relocation from profile.yaml), and what would change that.
"search_terms": 4-8 short phrases to type into justjoin.it or pracuj.pl search, Polish and English
mixed (e.g. "programista python", "python developer").
If a <desk> table is given, it shows how the candidate's captured postings actually scored per
title family: let it shift your advice."""


class Aim(BaseModel):
    title_en: str
    title_pl: str
    why: str
    evidence: list[str] = Field(min_length=1)  # facts it rests on; no evidence, no title


class NotThis(BaseModel):
    title_en: str
    why_not: str


class Advice(BaseModel):
    # ponytail: "one sentence, ~25 words" lives in the prompt only; a word-count validator would burn retries.
    aim_for: list[Aim] = Field(min_length=3, max_length=3)
    not_these: list[NotThis] = Field(min_length=2, max_length=3)
    search_terms: list[str] = Field(min_length=4, max_length=8)


# First match wins, so the broad families (frontend, python/backend) go last.
# ponytail: keyword families; a title with no keyword falls back to its tech (family()), then "other".
FAMILIES = {
    "fullstack": r"full ?stack",
    "qa/test": r"qa|test\w*|sdet|quality",
    "devops": r"devops|sre|platform|cloud|infrastructure",
    "data": r"data|danych|ml|machine learning|ai|analyst|analityk",
    "java/jvm": r"java|kotlin|scala|jvm|spring",
    "python/backend": r"python|django|fastapi|flask|back ?end",
    "frontend": r"front ?end|react|angular|vue|javascript|typescript",
}


def matching(text: str) -> str | None:
    t = re.sub(r"[\W_]+", " ", text.casefold())  # "Full-Stack" -> "full stack"; keeps Polish letters
    return next((f for f, kw in FAMILIES.items() if re.search(rf"\b(?:{kw})\b", t)), None)


def family(title: str, tech: list[str] = ()) -> str:
    """By title; a keyword-less title ("Software Engineer") falls back to its tech, then "other"."""
    # ponytail: first family in FAMILIES order wins, so "unit tests" in tech pulls a vague title into qa/test.
    return matching(title) or next((f for f in FAMILIES if any(matching(x) == f for x in tech)), "other")


def desk(postings: list[tuple[str, list[str], int]]) -> list[dict]:
    """(title, tech, score) triples -> count and average fit per family, best average first."""
    fams: dict[str, list[int]] = {}
    for title, tech, score in postings:
        fams.setdefault(family(title, tech), []).append(score)
    rows = [{"family": f, "count": len(s), "avg": round(sum(s) / len(s))} for f, s in fams.items()]
    return sorted(rows, key=lambda r: -r["avg"])


def advise(facts: str, table: list[dict], client: anthropic.Anthropic) -> tuple[Advice, object]:
    lines = "\n".join(f"{r['family']}: {r['count']} postings, average fit {r['avg']}" for r in table)
    return ask(client, MODEL, RULES, facts, lines or "No scored postings yet.", Advice, tag="desk")

