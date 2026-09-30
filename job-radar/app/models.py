from sqlmodel import create_engine

from app.settings import settings

# check_same_thread=False: sync endpoints run in FastAPI's threadpool.
engine = create_engine(
    f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False}
)
