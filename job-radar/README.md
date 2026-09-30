# job-radar

Local job-hunting tool. FastAPI + SQLite, runs on your machine only.

```sh
uv sync
uv run playwright install chromium
cp .env.example .env   # fill in
uv run python -m app.main   # http://127.0.0.1:8000/health
uv run pytest
```
