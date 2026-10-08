import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.types import Usage
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import main, models

EXAMPLE = Path(__file__).parents[1] / "profile.example.yaml"
CV = """lang: en
name: Jan Kowalski
contact: [[Kraków, jan@example.com]]
education: [{title: BSc Computer Science, right: 2020 – 2024, text: "", bullets: []}]
languages: Polish (native) · English (C1)
"""
RAW = SimpleNamespace(usage=Usage(input_tokens=10, output_tokens=5), model_dump_json=lambda: '{"raw": 1}')


class NoModel:
    @property
    def messages(self):
        raise RuntimeError("no model in tests")


@pytest.fixture
def api(monkeypatch, tmp_path):
    """The app on an in-memory DB, in a temp dir holding the example profile and a fake CV."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(models, "engine", engine)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "client", NoModel())  # a test that wants the model swaps in its own fake
    shutil.copy(EXAMPLE, "profile.yaml")
    Path("cv_en.yaml").write_text(CV, encoding="utf-8")
    return TestClient(main.app)
