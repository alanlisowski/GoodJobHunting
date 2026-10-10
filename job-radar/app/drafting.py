from typing import Literal

import anthropic
from pydantic import BaseModel

from app.scoring import ask

MODEL = "claude-opus-5-5"

RULES = """You tailor a candidate's CV and cover letter to one job posting.
The facts are the only truth: profile.yaml (constraints), cv_*.yaml (their real CVs),
profile_additions.yaml (their answers to earlier questions; an answer may say they lack something).
<notes> at the end of the posting, if present, are the candidate's own comments on this posting: follow
them, and treat what they say about themselves as facts.

- Write in the posting's language: pl or en. Start from the CV in that language and keep its
  wording where it fits. Reorder and select projects, skills and bullets so the most relevant come
  first; rewrite the headline and about for this role. The result must fit one A4 page:
  never longer than the base CV, shorter is fine.
- Every statement must be backed by a fact. Never invent or inflate skills, tools, years,
  results or responsibilities, and never imply experience the facts don't show.
- When the posting asks for something the facts don't cover, or cover only vaguely, leave it
  out of the CV and letter and add a gap: the requirement, and one short question whose
  answer would let the candidate claim it truthfully. Don't ask again what an answer already settled.
- Entries: use `text` for a paragraph or `bullets` for a list, leave the other empty.
- The letter: 3-4 short paragraphs of body text only (no greeting, no sign-off), specific to
  this company and role, same honesty rule."""


class Skill(BaseModel):
    label: str
    value: str


class Entry(BaseModel):
    title: str
    right: str  # link or dates
    text: str
    bullets: list[str]


class Gap(BaseModel):
    requirement: str
    question: str


class Tailored(BaseModel):
    lang: Literal["pl", "en"]
    headline: str
    about: str
    skills: list[Skill]
    projects: list[Entry]
    experience: list[Entry]
    letter: list[str]
    gaps: list[Gap]


def tailor(posting: str, facts: str, client: anthropic.Anthropic) -> tuple[Tailored, object]:
    return ask(client, MODEL, RULES, facts, posting, Tailored)


def cv_data(t: dict, base: dict) -> dict:
    """Template data: name, contact, portfolio, education, certificates, languages stay as the base CV has them."""
    return {**base, **{k: t[k] for k in ("lang", "headline", "about", "projects", "experience")},
            "skills": {s["label"]: s["value"] for s in t["skills"]}}
