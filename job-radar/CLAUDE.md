# job-radar

Local single-user app. It collects job postings, scores them against `profile.yaml`,
and drafts CVs and cover letters in PL or EN, with a human check wherever honesty matters.
Full plan: `../job-radar-plan.md`. The decisions below are settled. Don't reopen them.

## Decisions
- Python 3.12 + FastAPI + uvicorn on **127.0.0.1:8000 only**. Use `uv` for deps and runs,
  `ruff` for lint, `pytest` for tests, GitHub Actions for CI (the workflow is at the repo root).
- **Sync `def` endpoints only**, never `async def`. FastAPI runs them in a threadpool.
- Parsing: JSON-LD `JobPosting` first, then per-board BeautifulSoup + lxml
  (justjoin.it, pracuj.pl), then a generic fallback.
- Intake: a pasted URL or HTML, then later the MV3 extension button. **No crawling.**
  No LinkedIn scraping. No continuous crawling of the boards. Capture only when the user triggers it.
- SQLite via SQLModel. Tables: `Posting`, `PostingSource` (one posting → many sources),
  `Score`, `Draft`. Dedupe on company + normalized title + location.
- Model calls: Anthropic SDK, **forced tool use with a JSON schema**, validated by Pydantic.
  A cheap model for scoring, a stronger one for drafting.
- PDFs: Jinja2 HTML → Playwright sync Chromium `page.pdf()`, one A4 page.
- UI: Jinja2 pages + a ~10-line `fetch()` helper calling the JSON endpoints (`templates/_desk.html`). No SPA, no HTMX.
- Profile: hand-edited `profile.yaml`, validated by Pydantic at startup, gitignored.
  `profile.example.yaml` (fake data) is committed.
- Never auto-send or auto-submit anything. Drafts flag gaps and the user answers them.
- Milestone order: 0 skeleton → 1 parse → 2 profile → 3 scoring. **If the milestone-3 ranking
  is useless, stop.** The rest depends on it.

## Traps (these fail silently)
- **Polish glyphs vanish in PDFs** on CI or in containers. Bundle a `.woff2` in `app/static/fonts`
  and load it with `@font-face`. Never use system fonts. Test with "żarówka, ściąga, łódź".
- **Any website can POST to localhost.** The capture endpoint requires the `X-Capture-Token`
  header (compare with `secrets.compare_digest`). No permissive CORS.
- **The MV3 service worker dies** after 30s idle or on slow fetches. The extension only
  POSTs HTML. The endpoint returns 202 immediately and scores in a BackgroundTask.
- **The model returns almost-JSON.** Force tool use and validate with Pydantic. Store the
  raw response. Retry once, then set status `score_failed`. Never store garbage.
- **Scores go stale when the profile changes.** Store `profile_hash` (sha256) on every
  Score and Draft, show a "stale" badge, and offer a rescore button.
- **Don't re-fetch captured pages.** If HTML was sent, parse that HTML. Re-fetching gets a
  login wall or a JS shell. Reject (422) any posting with no title or an empty tech list.
- **Cost creeps.** Log input/output tokens per call and show a running total. Cache the
  profile as a system block (prompt caching).
- **Secrets:** `.env`, `profile.yaml`, `profile_additions.yaml`, `*.db` and `output/` never
  enter git. `ANTHROPIC_API_KEY` and `CAPTURE_TOKEN` are required and have no defaults.
  CI uses dummy values and mocks every model call.
- An `async def` handler with a blocking call freezes the server. SQLite needs
  `check_same_thread=False` (already set in `app/models.py`).
- Never pass `--host 0.0.0.0`. `uv run uvicorn app.main:app` defaults to 127.0.0.1:8000.
- Playwright needs `uv run playwright install chromium`. On Windows without uv on
  PATH, use `py -m uv`.
