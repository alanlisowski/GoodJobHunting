from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

MODEL = "claude-sonnet-5-5"  # plan: the cheap model scores, the strong one drafts

RULES = """You score a job posting against a candidate's facts: profile.yaml (constraints),
cv_*.yaml (their real CVs) and profile_additions.yaml (their answers to earlier questions).
Every requirement you count as met must cite the specific fact that proves it.
No citation, no credit: list it as missing instead.
A dealbreaker from profile.yaml that the posting hits caps the score at 20.
Be discriminating: use the whole 0-100 range, a weak fit is not a 70."""


class Met(BaseModel):
    requirement: str
    evidence_from_profile: str


class Missing(BaseModel):
    requirement: str
    severity: Literal["blocker", "minor"]


class Score(BaseModel):
    # ponytail: title/company extracted here instead of a parser; add parsers if these come out wrong.
    title: str
    company: str
    score: int = Field(ge=0, le=100)
    met: list[Met]
    missing: list[Missing]
    dealbreakers_hit: list[str]
    verdict: str


def ask[T: BaseModel](client: anthropic.Anthropic, model: str, rules: str, facts: str,
                      posting: str, schema: type[T], tag: str = "posting") -> tuple[T, object]:
    """One structured call: validated output and the raw response (for usage + storage)."""
    for _ in (1, 2):  # plan: retry once, then give up
        try:
            r = client.messages.parse(
                model=model,
                max_tokens=16000,
                # Facts are identical on every call: cache them.
                system=[
                    {"type": "text", "text": rules},
                    {"type": "text", "text": f"<facts>\n{facts}\n</facts>",
                     "cache_control": {"type": "ephemeral"}},
                ],
                messages=[{"role": "user", "content": f"<{tag}>\n{posting}\n</{tag}>"}],
                output_format=schema,
            )
            if r.stop_reason == "refusal":
                raise RuntimeError(f"model refused: {r.stop_details}")
            if r.parsed_output is not None:
                return schema.model_validate(r.parsed_output.model_dump()), r
            err = r.content
        except ValidationError as e:  # the SDK validates inside parse(): a bad shape raises there
            err = e
    raise ValueError(f"unparseable {schema.__name__} after retry: {err}")


def score(posting: str, facts: str, client: anthropic.Anthropic) -> tuple[Score, object]:
    return ask(client, MODEL, RULES, facts, posting, Score)
