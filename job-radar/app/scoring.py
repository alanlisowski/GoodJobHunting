from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

MODEL = "claude-opus-5-5"

RULES = """You score a job posting against a candidate profile.
Every requirement you count as met must cite the specific profile item that proves it.
No citation, no credit: list it as missing instead.
A dealbreaker from the profile that the posting hits caps the score at 20.
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


def score(posting: str, profile: str, client: anthropic.Anthropic) -> tuple[Score, object]:
    """Returns the validated score and the raw response (for usage + storage)."""
    for attempt in (1, 2):  # plan: retry once, then give up
        r = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            # Profile is identical on every call: cache it.
            system=[
                {"type": "text", "text": RULES},
                {"type": "text", "text": f"<profile>\n{profile}\n</profile>",
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": f"<posting>\n{posting}\n</posting>"}],
            output_format=Score,
        )
        if r.stop_reason == "refusal":
            raise RuntimeError(f"model refused: {r.stop_details}")
        try:
            if r.parsed_output is not None:
                return Score.model_validate(r.parsed_output.model_dump()), r
        except ValidationError:
            pass
        if attempt == 2:
            raise ValueError(f"unparseable score after retry: {r.content}")
