from datetime import UTC, datetime

from sqlmodel import JSON, Column, Field, SQLModel, create_engine

from app.settings import settings

# check_same_thread=False: sync endpoints run in FastAPI's threadpool.
engine = create_engine(
    f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False}
)


class Posting(SQLModel, table=True):
    # ponytail: posting + its latest score in one row; split out Score when rescore history matters.
    id: int | None = Field(default=None, primary_key=True)
    text: str
    title: str
    company: str
    score: int = Field(index=True)
    verdict: str
    result: dict = Field(sa_column=Column(JSON))  # full Score: met / missing / dealbreakers
    usage: dict = Field(sa_column=Column(JSON))  # token counts, for the cost total later
    model: str
    profile_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
