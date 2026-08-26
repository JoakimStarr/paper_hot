# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

PaperPulse (repo: `paper_hot`) is a minimal academic-paper analysis platform for economics researchers. It aggregates papers from CNKI TOP50 economics journals, 6 economics journal sites, and arXiv; provides AI analysis, topic/discussion dialogue, similarity matching, trend analysis, and keyword/author network visualization. Product vision: reposition from "paper discovery" to a "research-topic brain" (see `PRODUCT_PLAN.md`).

## Commands

### Environment setup
```bash
# One-shot install (creates venv + server deps; crawler libs NOT installed)
./install.sh --base-only
# Or with local embedding model (Ollama + bge-m3, fully offline, no API cost):
./install.sh --with-ollama

# Configure AI keys (at least one provider) before running:
cp backend/.env.example backend/.env   # then edit ZHIPU_API_KEY / SILICONFLOW_API_KEY
```

Dependencies are split into two files and are intentionally decoupled:
- `requirements.txt` (and `backend/requirements.txt`) — **server deps only** (FastAPI, SQLAlchemy asyncio, aiosqlite, AI, scikit-learn, jieba). Required.
- `requirements-crawler.txt` — **crawler-only deps** (arxiv, DrissionPage, bs4, playwright, ddddocr). Optional; only needed to actually crawl.

### Run the app (uses the existing `venv/`)
```bash
./start.sh start     # production (builds frontend, no HMR)
./start.sh dev       # dev mode (clears .next, HMR)
./start.sh stop      # stop all
./start.sh restart [dev|prod]
./start.sh status
```
Backend serves on `:8000`, frontend on `:3000` (both configurable via `backend_port`/`frontend_port` in `backend/.env`; ports auto-shift if busy). API docs at `http://localhost:8000/docs`. The frontend proxies `/api` to the backend at runtime (via `BACKEND_API_URL` + Next rewrites), so backend port changes don't require a frontend rebuild.

### Backend tests (pytest)
Run from the `backend/` directory so the `app` package is importable:
```bash
cd backend && ../venv/bin/python -m pytest tests/ -q
# single test file:
../venv/bin/python -m pytest tests/test_scoring.py -q
# single test:
../venv/bin/python -m pytest tests/test_scoring.py::test_final_score_weights -q
```
There is no `conftest.py` or `pytest.ini`; tests live in `backend/tests/` and are plain `test_*.py` files. `app` is importable because `backend/` is the working directory.

### Frontend (Next.js 14, TypeScript)
```bash
cd frontend
npx tsc --noEmit     # type check (primary frontend validation — see note below)
npm run lint         # next lint
npm run build        # production build
npm run dev          # dev server
```

### Docker
```bash
docker compose up -d   # builds/runs both images; SCHEDULER_ENABLED=false by default
```

## Architecture

### Backend (FastAPI + async SQLAlchemy / aiosqlite)
Entry points and wiring:
- `backend/app/main.py` — FastAPI app + lifespan. On startup it runs `init_db()`, zombie-report cleanup, stale-crawl-log cleanup, and `scheduler.run_startup_maintenance()` (always runs even when the scheduler is disabled). CORS allows any `localhost`/`127.0.0.1` port. All routes mounted under `/api`.
- `backend/app/api.py` — aggregates the routers in `backend/app/routers/`.
- `backend/app/config.py` — pydantic-settings `Settings`, reads `backend/.env`. All tunables live here (AI keys, model priority, `scheduler_enabled`, ports, `embedding_model`, `default_model` as `provider/model`).

Data layer:
- `backend/app/database.py` — async engine + `AsyncSessionLocal` + `get_db` dependency. DB is a single **SQLite** file at `backend/data/paperpulse.db` (Postgres URL supported via `DATABASE_URL` but SQLite is the deployed target).
- `backend/app/models.py` — ORM models (~20 tables: `Paper`, `PaperFeatures`, `PaperScore`, `PaperSimilarity`, `TopicTrend`, `CrawlLog`, `AIAnalysisReport`, `TopicProject`, `Favorite`, `ReadingHistory`, `FollowedSubfield`, `ReviewReport`, `BatchReport`, etc.). `UnicodeJSON` is a custom `TypeDecorator` that stores already-serialized JSON as text to avoid double-encoding — preserve this when touching JSON columns.
- `backend/app/crud.py` — **single source of truth for scoring** (see below) plus keyword-frequency aggregation and crawl-log helpers.

Business logic:
- `backend/app/scoring.py` (`ScoringSystem`) — thin wrapper that delegates to `PaperCRUD`'s static methods. After P0-1 unification there is ONE scoring formula: weights `0.35/0.35/0.30` (recency/venue/trend) with a 180-day recency half-life. Do not add a second scoring formula.
- `backend/app/similarity.py` — jieba tokenization + TF-IDF + cosine similarity. `compute_all_similarities` keeps Top-20 per paper above a 0.1 threshold; `compute_and_store_for_paper` is the per-paper incremental path used after crawls/abstract backfills.
- `backend/app/ai_processor.py` (`AIProcessor`) — keyword extraction, topic classification (AI/CS topics + economics subfields via keyword dictionaries), and `compute_embedding` which delegates to `ai_service.embed_texts`.
- `backend/app/ai_service.py` (`AITrendService`) — **all AI calls go through here** via the OpenAI-compatible interface (zhipu / siliconflow / openai / custom providers). Handles provider initialization, model-priority ordering, fallback across providers/models, structured JSON parsing, and embeddings (`embed_texts`). Singleton `ai_trend_service` is imported across the app; reload via `ai_trend_service.reload()` after settings change.
- `backend/app/scheduler.py` (`PaperScheduler`, APScheduler) — crawl/refresh jobs with **lazy imports** of the crawler modules (`app.fetchers`, `app.fetchers_cnki*`) so a server without crawler deps still boots. Jobs: fetch arXiv (24h), update trends (6h), fetch economics journals (cron 02:00), backfill abstracts (cron 03:30). Shared ingestion path `_process_and_score_paper` is used by every crawler.

Routers (`backend/app/routers/`): `papers` (discovery/filter/search), `ai` (SSE streaming single-paper analysis + follow-up chat), `network` (D3 keyword/author maps), `crawler` (manual crawl trigger + similarity recompute), `topic` (topic validator / gap analysis / 选题), `personal` (favorites, reading history, followed subfields), `dashboard` (research workbench), `producer` (literature-review / 综述 generation).

Crawlers (heavy deps, lazy-imported): `app/fetchers.py` (arXiv + 6 economics journals via bs4), `app/fetchers_cnki.py` / `app/fetchers_cnki_navi.py` (CNKI via DrissionPage), `cnki_paper_captcha.py` (root; standalone CNKI keyword search + ddddocr captcha). `backend/scripts/cleanup_data_quality.py` is a one-off data cleanup script.

### Frontend (Next.js 14 App Router, React 18, TypeScript, Tailwind, D3)
- Routes under `frontend/src/app/`: `page.tsx` (home/discovery), `paper/`, `author/`, `search/`, `trends/`, `network/`, `topics/`, `dashboard/`, `reading/`, `system/`.
- `frontend/src/lib/`: `api.ts` (unified fetch layer + SSE stream parsing), `i18n.ts` (`useLanguage().t` — i18n is partial; several new pages still hardcode Chinese), `user.ts` (generates local `userId`), `cache.ts` (localStorage — being superseded by backend-backed favorites), `utils.ts` (docx/BibTeX export).
- Shared components in `frontend/src/components/` (e.g. `PaperCard`, `Filters`, `Layout`). The primary frontend validation is `npx tsc --noEmit` (there is no test suite on the frontend).

## Key conventions / gotchas (read before editing)

- **Crawler/server dependency decoupling is intentional.** Never add a top-level `import` of a crawler module (DrissionPage, arxiv, bs4, playwright, ddddocr) into `main.py`, `api.py`, `routers/`, `crud.py`, `ai_service.py`, etc. Keep them inside functions so a crawler-less server still imports cleanly.
- **Embeddings are model-specific.** Stored as JSON strings in `paper_features.embedding`. After switching `embedding_model`, back up the DB, clear `paper_features.embedding`, restart, then trigger a full rebuild via `POST /api/topic-validator/embeddings/backfill`. Vectors from different models are incompatible.
- **Lightweight user model, no real auth.** Identity is a `user_id` passed in the `x-user-id` header (defaults to `"local"`; frontend generates one in localStorage). All personal tables (favorites, reading history, followed subfields, `topic_projects`, `review_reports`) are keyed by `user_id`. Don't assume a global single user in new endpoints.
- **`backend/.env` must only contain keys declared in `Settings`** (pydantic-settings forbids extra fields in the installed pydantic version). An unrecognized key (e.g. the local `cnki_url_prefix=...` currently in this repo's `.env`) raises `ValidationError` on `import app.config` and breaks collection of the 3 test files that import routers (`test_advanced_search`, `test_new_endpoint_helpers`, `test_topic_brief`). Remove/ignore stray keys before running those tests.
- **Startup maintenance runs regardless of `scheduler_enabled`.** Trend refresh + incremental embedding backfill always run on boot; the scheduler (active crawling) is gated by `SCHEDULER_ENABLED` (default `true` in `config.py`, but production/README guidance sets it `false` on servers since crawling is done elsewhere).
- **Brand name inconsistency:** UI shows "ApplePaper" in places while README/config call it "PaperPulse" (`PRODUCT_PLAN.md` issue #148). Be aware when searching strings.
- **AI is the differentiating asset.** Single-paper analysis usage was historically very low; product direction (P0–P2 in `PRODUCT_PLAN.md`) is to surface AI at the list/dashboard level and build the "topic brain" closed loop (trends → gaps → validation → journal fit → review export). Prefer reusing `AITrendService` over adding direct provider calls.
- **Data-quality boundaries that are deliberately NOT fixed** (see `KNOWN_ISSUES.md`): 经济学季刊 abstracts are intentionally left empty (only 2 papers, fixing needs browser-session crawling); CNKI captcha auto-solving is guard-implemented and falls back to manual — it needs real-CNKI tuning.
