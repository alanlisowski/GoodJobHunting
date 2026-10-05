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

## Extension (one-click capture)

1. `chrome://extensions` → Developer mode → **Load unpacked** → `job-radar/extension/`.
2. Extension options: paste `CAPTURE_TOKEN` from `.env`.
3. On a posting, click the icon: ✓ means queued; it shows up scored on the desk in ~30s.
   A number on the badge is the HTTP error (401: wrong token); ✗: the app isn't running.
