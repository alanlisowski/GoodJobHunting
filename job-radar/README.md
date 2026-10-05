[![CI](https://github.com/alanlisowski/GoodJobHunting/actions/workflows/ci.yml/badge.svg)](https://github.com/alanlisowski/GoodJobHunting/actions/workflows/ci.yml)

# job-radar

Local job-hunting tool. FastAPI + SQLite, runs on your machine only.

```sh
uv sync
uv run playwright install chromium
cp .env.example .env   # fill in
uv run python -m app.main   # http://127.0.0.1:8000/health
uv run pytest
uv run python -m app.render cv_pl.yaml output/cv_pl.pdf   # CV data (gitignored) -> one A4 page
```
