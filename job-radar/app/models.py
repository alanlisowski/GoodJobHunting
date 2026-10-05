from datetime import UTC, datetime
from typing import Literal

from sqlmodel import JSON, Column, Field, SQLModel, create_engine

from app.settings import settings

# check_same_thread=False: sync endpoints run in FastAPI's threadpool.
engine = create_engine(
    f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False}
)


Status = Literal["new", "shortlisted", "applied", "interview", "rejected", "ignored"]


def migrate(engine) -> None:
    """create_all never alters an existing table: add columns newer than the user's database."""
    # ponytail: hand-rolled ALTERs; switch to Alembic when a change needs more than ADD COLUMN.
    with engine.begin() as c:
        if "status" not in {row[1] for row in c.exec_driver_sql("PRAGMA table_info(posting)")}:
            c.exec_driver_sql("ALTER TABLE posting ADD COLUMN status VARCHAR NOT NULL DEFAULT 'new'")


class Posting(SQLModel, table=True):
    # ponytail: posting + its latest score in one row; split out Score when rescore history matters.
    id: int | None = Field(default=None, primary_key=True)
    text: str
    title: str
    company: str
    score: int = Field(index=True)
    verdict: str
    result: dict = Field(sa_column=Column(JSON))  # full Score: met / missing / dealbreakers
    usage: dict = Field(sa_column=Column(JSON))  # token counts, summed by GET /usage
    raw: str  # full model response, to debug a bad score
    model: str
    profile_hash: str
    status: str = "new"  # a Status; checked at the endpoint, plain str in the table
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Draft(SQLModel, table=True):
    # Many per posting: regenerating after answering gaps adds a row; the newest one counts.
    id: int | None = Field(default=None, primary_key=True)
    posting_id: int = Field(foreign_key="posting.id", index=True)
    data: dict = Field(sa_column=Column(JSON))  # Tailored: CV sections, letter, gaps
    raw: str
    usage: dict = Field(sa_column=Column(JSON))
    model: str
    profile_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
