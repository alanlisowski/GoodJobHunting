# job-radar

Local, single-user FastAPI app. Python 3.12, managed with uv.

## Decisions
- **uv** for everything: `uv add`, `uv run`. No pip/requirements.txt.
- **Sync `def` endpoints only.** No `async def`. FastAPI runs them in a threadpool,
  so blocking calls (SQLite, sync httpx, the sync Anthropic client) are fine.
- **SQLModel on SQLite** at `DB_PATH` (default `./job_radar.db`).
- **Settings** via pydantic-settings from `.env` (`app/settings.py`).
- **Bind 127.0.0.1:8000 only.** Start with `uv run python -m app.main`.
- Parsing code lives in `app/parsing/`. Tests live in `tests/`.
- CI (`.github/workflows/ci.yml`) runs `ruff check` and `pytest`.

## Traps
- `async def` + a blocking call freezes the whole server. Stay sync.
- SQLite + threadpool needs `check_same_thread=False` (already set in `app/models.py`).
- Never bind `0.0.0.0` or `--host` anything else: `CAPTURE_TOKEN` is the only auth.
- `ANTHROPIC_API_KEY` and `CAPTURE_TOKEN` are required. Don't give them defaults.
  Compare tokens with `secrets.compare_digest`.
- Importing `app.settings` or `app.models` needs env vars. Keep `/health` import-free
  so tests and CI run without `.env`. CI sets dummy values anyway.
- Never commit `.env`, `profile.yaml` (personal data), `*.db`, `output/`.
- Playwright needs browsers: `uv run playwright install chromium`. CI skips this.
- Windows: if `uv` isn't on PATH, use `py -m uv`.
