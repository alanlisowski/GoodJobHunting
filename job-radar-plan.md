# Job Radar — build plan (v2, Python)

_Rewritten 2026-09-30 from the original "Job Radar — build plan" doc. All Java/Spring leftovers removed; additions are marked **[new]**._

Job Radar is a local Python app. It collects job postings from job listing sites, scores them against your real background, and drafts tailored CVs and cover letters in Polish or English. A human check sits wherever honesty matters. A thin Chrome extension, added later, is the button that brings pages from your own browser into the app.

---

## 1. Decisions (settled, don't reopen)

| Decision | Chosen | Why |
|---|---|---|
| Form | Local app + thin Chrome extension later | MV3 has no reliable background; the app needs an API key, a database and PDF rendering |
| Language | Python 3.12 + FastAPI, served by uvicorn on `127.0.0.1:8000` | Fastest path to the milestone that decides the project. The Java gap gets its own small project instead |
| Sync vs async | **Plain sync endpoints** (`def`, not `async def`) **[new: was open]** | One user; sync is simpler to write, test and debug. FastAPI runs sync handlers in a threadpool, so slow model calls don't freeze the server |
| Parsing | JSON-LD `JobPosting` first, then BeautifulSoup + lxml selectors per board **[new]** | Most boards embed schema.org JSON-LD; it's more stable than their CSS classes |
| Sources | Paste a URL or HTML first, then extension capture for justjoin.it and pracuj.pl | Their terms forbid automated harvesting. A button you press in your own browser is you reading a page |
| Database | SQLite through SQLModel | One file to back up, typed models shared with FastAPI, fine for thousands of postings |
| Model calls | Anthropic Python SDK, structured output via tool use with a JSON schema | No regex-parsing free text |
| PDFs | Jinja2 HTML template → headless Chromium via Playwright (`page.pdf()`) | Handles Polish, and you already render CVs with headless Chromium |
| UI | Jinja2 templates + HTMX | This is not the part that needs React |
| Profile | One YAML file you hand-edit, validated by Pydantic at startup, **gitignored** **[new: was open]** | Honest, diffable, versionable. The desk can edit it later if hand-editing gets annoying |
| Tooling **[new]** | `uv` for env/deps, `ruff` for lint+format, `pytest`, GitHub Actions | Standard modern Python and what a reviewer expects to see |
| Applications | Drafts with gaps flagged, never auto-sent | The quality came from you answering gap questions. A silent generator invents |
| Auto-submit forms | Out of scope | Bans, ToS, and mass applying lowers your hit rate |

**The Java/Kotlin gap:** close it separately and cheaply. Rewrite the Android dice game in Kotlin, or build a small Spring Boot service with JUnit + Mockito. Either is a weekend and earns the same CV line. Book it as its own weekend rather than assuming it will happen.

---

## 2. What it will and won't do

**It will**
- Take a posting URL or pasted HTML and store title, company, location, work mode, salary, required tech, nice-to-haves, deadline and the ad's language.
- Score each posting against your profile and say **why**: which requirements you meet and which you don't, each one cited.
- Keep everything in one searchable place with a status per posting: `new → shortlisted → applied → interview → rejected / ignored`.
- **[new] Deduplicate:** the same role on justjoin.it and pracuj.pl becomes one posting with two sources, matched on company + normalized title + location.
- Draft a tailored CV and cover letter in the posting's language and render them to a one-page A4 PDF.
- Mark every claim it can't verify from your profile, so you fill it in rather than the model guessing.
- Accept postings captured by the one-button extension from pages you open yourself.

**It won't**
- Crawl LinkedIn. It's blocked in robots.txt, forbidden by its terms, and accounts that scrape get banned. LinkedIn postings come in by paste or by the extension button.
- Continuously crawl pracuj.pl or justjoin.it. Capture is something you trigger while looking at a page.
- Submit anything: no auto-apply, no form filling, no sending email.
- Write a finished application unattended. The model drafts, you answer the gap questions, then it finalises. That loop is the product.

**Later, legitimately:** if you want broader automatic intake, the clean routes are the official board APIs (Greenhouse, Lever and Workable publish per-company JSON feeds) and an email-alert inbox parser. Both are allowed and neither needs scraping.

---

## 3. Architecture

```
 paste URL/HTML ─┐
 extension POST ─┴─► parser ─► postings (SQLite) ─► scorer ─► ranked desk ─► drafter ─► gap questions ─► you ─► PDF
                    (JSON-LD → BS4)                (Claude + profile.yaml)            (Claude)                (Playwright)
```

Everything runs on `127.0.0.1`: nothing is exposed and nothing is submitted.

**[new] Repo layout**
```
job-radar/
  app/
    main.py            # FastAPI app, routers
    models.py          # SQLModel tables
    parsing/           # jsonld.py, boards/justjoin.py, boards/pracuj.py, generic.py
    scoring.py         # prompt assembly + tool-use call + validation
    drafting.py        # CV/letter drafting, gap extraction
    render.py          # Jinja → Playwright → PDF
    profile.py         # Pydantic profile schema + loader
    templates/         # desk pages + cv_pl.html, cv_en.html, letter_*.html
  extension/           # MV3: manifest.json, background.js, content.js
  tests/fixtures/      # saved HTML per board, sample profile
  profile.example.yaml # committed; profile.yaml is gitignored
  .env.example         # ANTHROPIC_API_KEY=, CAPTURE_TOKEN=
  CLAUDE.md
```

**[new] Core data model**
- `Posting`: id, title, company, location, work_mode, salary_min/max/currency, required_tech[], nice_to_have[], deadline, language, status, raw_html_path, created_at
- `PostingSource`: posting_id, board, url, captured_at (one posting → many sources)
- `Score`: posting_id, **profile_hash**, model, score 0–100, met[], missing[], verdict, raw_response, created_at
- `Draft`: posting_id, kind (cv/letter), language, body_html, open_gaps[], pdf_path, profile_hash

---

## 4. The traps

These fail quietly, with no exception, just a wrong result you notice a week later.

**Polish characters vanish from your PDFs.** Chromium renders whatever fonts the machine has. Locally you're fine, which is exactly why it breaks the first time you run it in CI or a container. Declare a specific font in the template (e.g. `@font-face` pointing at a bundled Noto Sans / Inter `.woff2` in the repo) instead of relying on system fonts. Your first render test is a PDF containing "żarówka, ściąga, łódź" that you open and look at. Do it in milestone 4, not later.

**The MV3 service worker dies mid-job.** 30 seconds of inactivity shuts the worker down, a single request over 5 minutes is killed, a fetch whose response takes over 30 seconds is abandoned, and `chrome.alarms` has a 30-second minimum period. The failure mode is silence. Keep the extension's job to "read this page's HTML, POST it to `127.0.0.1:8000`, show a checkmark", and make the endpoint return immediately; score afterwards in the app.

**[new] Any website can POST to your localhost.** A page you visit can fire a request at `127.0.0.1:8000`. Require a shared `X-Capture-Token` header (from `.env`, pasted once into the extension's options) on the capture endpoint, and don't enable permissive CORS.

**The model returns JSON that is almost JSON.** Use tool use with an input schema, validate the result with Pydantic, and store the raw response next to the parsed one. On a validation failure, retry once and then mark the posting `score_failed` rather than storing garbage.

**Scores drift silently as you edit the profile.** Store a hash of the profile file with every score and draft. Show "stale" in the desk when the hash differs, and offer a rescore button.

**Read the page, don't re-fetch it.** When the extension sends captured HTML, parse that HTML. If the app fetches the same URL itself it gets a login wall or a JavaScript shell, and BeautifulSoup will happily parse that shell into an empty posting. Reject any posting with no title or no tech list rather than saving it.

**[new] Model cost creeps.** Scoring every captured posting with a big model adds up. Log input/output tokens per call, show a running total in the desk, use a cheaper model for scoring and a stronger one only for drafting, and use prompt caching for the profile, which is the same on every call.

**Don't commit your API key, and don't listen beyond localhost.** Bind to 127.0.0.1, keep the key in `.env`, and put `.env` and `profile.yaml` in `.gitignore` from the first commit. This repo is going in your portfolio.

---

## 5. Milestones, each with a Claude Code prompt

Ordered so the question that decides whether this is worth finishing gets answered third. Each one ends in something you can look at. Paste the prompt into Claude Code in the repo; each assumes the previous milestones exist.

### 0. Skeleton **[new]**
Repo, tooling and guard rails before any feature.
*Done when:* `uv run pytest` passes an empty test, `ruff check` is clean, `uv run uvicorn app.main:app` serves `GET /health` on 127.0.0.1:8000, and `.env` and `profile.yaml` are gitignored.

> Set up a new Python 3.12 project called job-radar using uv. Add FastAPI, uvicorn, SQLModel, pydantic-settings, beautifulsoup4, lxml, httpx, pyyaml, jinja2, anthropic, playwright; dev deps pytest, ruff. Create the layout: app/main.py with a GET /health endpoint, app/models.py, app/parsing/, tests/. Settings via pydantic-settings reading .env (ANTHROPIC_API_KEY, CAPTURE_TOKEN, DB_PATH default ./job_radar.db). Uvicorn must bind 127.0.0.1:8000. .gitignore must include .env, profile.yaml, *.db, output/. Add .env.example, a README stub, a CLAUDE.md summarising this plan's decisions and traps, and a GitHub Actions workflow running ruff and pytest. Use sync (def) endpoints throughout.

### 1. A posting goes in, structured data comes out
*Done when:* you paste the Putka posting, then the CTHINGS one, and `GET /postings` returns both with title, company, location and tech list correct.

> Add POST /postings accepting either {url} or {html, url}. If only a URL is given, fetch it with httpx; if html is given, never re-fetch. Parse JSON-LD JobPosting first (app/parsing/jsonld.py), then fall back to board-specific BeautifulSoup parsers for justjoin.it and pracuj.pl, then a generic fallback. Store a Posting and a PostingSource in SQLite via SQLModel, save the raw HTML to disk, detect the ad language (pl/en). Reject with 422 when title or tech list is empty. Dedupe on company + normalized title + location by attaching a new source instead of a new row. Add GET /postings and GET /postings/{id}. Write pytest tests using saved HTML fixtures in tests/fixtures/.

### 2. Your profile, as a file the app reads
The asset the whole thing runs on, and writing it is the most valuable hour of the project: languages with honest levels, projects with the specific mechanisms you built, certificates, location and work-mode constraints, salary floor, and hard no-gos.
*Done when:* the app loads it at startup, `GET /profile` returns it, and a missing required field fails loudly at boot.

> Define a Pydantic schema for profile.yaml in app/profile.py: personal (name, city, languages with CEFR levels), work_constraints (work modes, max commute, relocation, salary floor PLN), skills (name, level 1–5, years, evidence), projects (name, stack, what I built, links), experience, education, certificates, dealbreakers. Load it at startup and fail with a clear error on invalid or missing fields. Compute a sha256 profile_hash. Add GET /profile. Commit profile.example.yaml with fake data; profile.yaml stays gitignored.

### 3. Scoring, and the honest go/no-go
Send posting + profile to the model and get back a score, the requirements met, the ones missing and a one-line verdict. Run it over the ten postings from this month. You already know the right answers for those, which makes them a free test set.
*Done when:* you can compare its ranking to your own judgement. **Stop here if the ranking is useless.** If it can't tell that Putka was your best fit and the Knowit Copilot role was not, the rest is decoration on a bad signal.

> Add app/scoring.py. Call the Anthropic API with a tool whose input schema is {score: 0-100, met: [{requirement, evidence_from_profile}], missing: [{requirement, severity: blocker|minor}], dealbreakers_hit: [], verdict: string}. Force tool use. The system prompt must require citing a specific profile item for every point given, and apply dealbreakers as hard caps. Put the profile in a cached system block. Validate with Pydantic, retry once on failure, and store Score with profile_hash, model, token usage and raw response. Add POST /postings/{id}/score and GET /postings?sort=score. Add scripts/eval_ranking.py that scores the postings in tests/fixtures/eval/ and prints the ranking next to my expected order from expected.yaml, with Spearman correlation.

### 4. A PDF you would actually send
Render the CV and letter from HTML templates using the tailoring rules, in the posting's language, on one A4 page.
*Done when:* the Polish PDF shows żarówka correctly and the layout matches what you've been sending this month.

> Add app/render.py: render Jinja2 templates (cv_pl.html, cv_en.html, letter_pl.html, letter_en.html) and print to A4 PDF with Playwright's sync Chromium API. Bundle a Unicode font as .woff2 in app/static/fonts and load it via @font-face; never rely on system fonts. Add a test that renders "żarówka, ściąga, łódź" and asserts the text is extractable from the PDF (pypdf) and the PDF is exactly one page.

### 5. The gap loop
The draft marks every claim it couldn't support from your profile. The app shows those as questions, your answers go back into the profile, and the draft regenerates.
*Done when:* a posting requiring a framework you don't have produces a question rather than an invented sentence.

> Add app/drafting.py. Draft CV bullet selection and a cover letter via tool use returning {sections, claims: [{text, supported_by: profile_ref | null}]}. Any claim with supported_by null becomes an open gap question and is excluded from the rendered PDF. Add endpoints to list gaps for a draft and to answer one; answers are appended to a profile_additions.yaml (gitignored) that is merged into the profile at load, and the draft regenerates. Store profile_hash on each Draft.

### 6. A desk you can work at
One page listing postings by score with status, a detail view, and links to the generated PDFs.
*Done when:* you run your next real application entirely through it, start to finish.

> Build the desk with Jinja2 + HTMX: a list page sorted by score with status filter, search, a "stale" badge when a score's profile_hash differs from the current one, and a running API-cost total; a detail page showing parsed fields, score reasoning (met/missing), draft PDFs, gap questions with answer forms, and status buttons. A paste box on the list page posts to /postings.

### 7. Tests worth showing a recruiter
pytest over the parsers, prompt assembly, scoring validation and the PDF renderer; saved HTML fixtures per board so a markup change fails a test instead of silently storing junk; model calls mocked in CI; GitHub Actions on push. Don't let this slide to the end: add tests alongside each milestone and use this one to fill gaps and add the badge.
*Done when:* the badge is green and `pytest` passes on a clean clone without an API key.

> Audit test coverage. Make sure every parser has a fixture test, scoring and drafting are tested with a mocked Anthropic client (recorded responses in tests/fixtures/llm/), the renderer test runs in CI (install Playwright Chromium in the workflow), and nothing in CI needs ANTHROPIC_API_KEY. Add a coverage report and the Actions badge to the README.

### 8. The extension button
Manifest V3, one action: read the current page's HTML, POST it to the app, show a checkmark.
*Done when:* you're on a justjoin.it posting, you click it, and the posting appears scored in your desk.

> Build extension/ as a Manifest V3 Chrome extension. On action click, use chrome.scripting.executeScript to grab document.documentElement.outerHTML and location.href from the active tab, then fetch POST http://127.0.0.1:8000/postings with header X-Capture-Token from chrome.storage (set on an options page). host_permissions: http://127.0.0.1:8000/*. Show ✓ or ✗ on the badge. The app endpoint must verify the token, return 202 immediately, and score in a FastAPI BackgroundTask. No long-running work in the service worker.

Stop planning past milestone 3 if the scoring disappoints you. That answer reshapes everything after it.

---

## 6. Risks

- **The scoring is mush.** This is the most likely failure: a model given a posting and a profile tends to say everything is a 7. Force it to cite a specific requirement and profile item for every point, apply dealbreakers as hard caps, and measure against the ten postings you have opinions about (milestone 3's eval script).
- **The Java gap stays open.** Your GitHub still has no modern JVM project when the next EPAM-type role appears. Book the Kotlin weekend.
- **The boards change their markup.** Fixture tests plus the "no title or no tech list means reject" rule catch it. JSON-LD-first parsing makes it rarer.
- **You finish it and stop job hunting.** The project is more fun than applying. Watch for it: milestone 6's "done" is a real application, not a feature.

## 7. Open questions (still undecided)

- [ ] **Which models, and what does one scoring run cost?** Default proposal: a small/cheap Claude model for scoring and a stronger one for drafting. Measure real token counts on the 10-posting eval before committing; check current prices on Anthropic's pricing page at that point.
- [ ] **Public repo or private?** Public makes it portfolio material and forces a good README. Either way, profile.yaml, profile_additions.yaml and .env never enter the repo.
- [ ] **Polish and English templates from day one, or English first?** Recommendation: both from day one. The font trap only shows up in Polish, so you want it early.

_Resolved in this rewrite: sync vs async (sync), where the profile lives (YAML + Pydantic, gitignored), port (8000, FastAPI/uvicorn default)._
