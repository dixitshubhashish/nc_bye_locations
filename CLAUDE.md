# CLAUDE.md

Running context file for Claude Code sessions working on this repo. Keep this updated as work progresses — append to the Work Log, don't rewrite history. See `README.md` for the user-facing overview.

## Project Snapshot

Web-based restaurant/location data platform (Birdeye competitive whitespace assessment). Python HTTP server (`whitespace_tool/workflow_server.py`) + vanilla HTML/JS frontend (`ui/`), backed by BigQuery in a Bronze/Silver/Gold medallion layout, with a SQLite mirror cache for fast reporting.

- **Entry point:** `python -m whitespace_tool workflow-ui --host 127.0.0.1 --port 8765`
- **Main branch for active work:** `develop`
- **Backend:** `whitespace_tool/workflow_server.py` (single large file, HTTP handlers + business logic)
- **Frontend:** `ui/index.html` (Mapper), `ui/integrations.html` (Reporting), `ui/login.html`, `ui/js/{mapper,reporting,review,templates,common}.js`
- **Tests:** `unit_tests/` — 135 tests, mocked BigQuery, run with `pytest unit_tests/ -q`

## Architecture (see README.md for full detail)

- **Bronze** (`birdeye_bronze_listings`): raw ingested tables (`listings`, `businesses`, `error_listings`, `us_zipcodes`, `workflow_templates`, `field_catalog`, `source_types`)
- **Silver** (`birdeye_silver_listings.listings_enriched`): validated + coordinate-enriched + enrichment status tagged (`fully_enriched`/`geo_enriched`/`zip_enriched`/`city_enriched`/`minimal`)
- **Gold** (`birdeye_gold_listings`): 6 pre-aggregated views (`vw_zip_brand_activity`, `vw_state_summary`, `vw_city_summary`, `vw_brand_summary`, `vw_listing_quality_summary`, `vw_geo_reference`)
- **SQLite mirror** (`.cache/whitespace_cache.db`): local copy of gold views, synced on every silver/gold rebuild, for sub-ms reporting
- **Refresh:** hourly background thread + on-demand ("Refresh Reports" button), sharing `REPORTING_REFRESH_LOCK`

## Known Gotchas / Lessons Learned

- **`make_handler(ui_dir)` closure vs `self.ui_dir`:** `MapperHandler.__init__` never sets `self.ui_dir` — `ui_dir` is only the outer closure variable. Any code inside the handler class must reference the bare `ui_dir` closure variable, not `self.ui_dir`. Using `self.ui_dir` raises `AttributeError` inside `__init__`'s call chain (since `socketserver` calls `self.handle()` synchronously from `__init__`), which manifests as "Empty reply from server" / connection reset for the affected route — this crashed the entire login flow once before (see Work Log 2026-09-06 fix).
- **Session cookie + `fetch()` redirects don't mix well:** returning a `302` to `/login` from a JSON API endpoint doesn't work cleanly with `fetch()`, which follows redirects by default and then tries to `.json()` parse the login page's HTML — producing a cryptic parse error, not a clean "please login" message. API endpoints should always return a JSON error body (401) on auth failure; only full-page navigations (`/app`, `/`, `/login`) should 302-redirect.
- **Cloud IDE ("antigravity") environment resets:** several commits in the log (`de70724`, `cc8b748`, `4b0d30e`, `9f47fb5`) were recovery fixes for corrupted/reset state after cloud IDE sessions — JS syntax corruption, logo/login regressions, mapping issues. A `.claude/hooks/session-start.sh` SessionStart hook now auto-installs deps and sets `PYTHONPATH` at session start to reduce recurrence of "server won't start" issues (added 2026-09-06).
- Sample/demo brand names were deliberately changed away from real brand names Domino's/Pizza Hut/Little Caesars (now Starlight Pizza Co./Crimson Slice/Pinnacle Pizza) to avoid confusion with the real assessment brands.
- Run `pytest unit_tests/ -q` after any backend change — should stay at 135 passed. All BigQuery access is mocked in tests, no live credentials needed.
- When testing the server manually in this sandbox, prefer `nohup ... & disown` over a plain trailing `&` in the same compound command — background job control quirks in this container can otherwise return a non-zero exit code from the launching command even though the server starts fine.

## Work Log

### 2026-09-06 — Enrichment metrics + Reporting tab
- Added `enrichment_status` field to `listings_enriched` (fully/geo/zip/city-enriched, minimal) based on coordinate presence and source.
- Expanded `data_quality_query` to compute enrichment level percentages and coordinate-source distribution (source_listing / zip_centroid / city_state_centroid).
- Added a Data Enrichment & Quality section to the Reporting tab UI (`ui/integrations.html`) with overall %, per-level breakdown, coordinate source split, and data quality metrics.
- Added `populateEnrichmentMetrics()` and `loadReporting()` in `ui/js/mapper.js` to fetch and render this data.

### 2026-09-06 — SessionStart hook for cloud IDE reliability
- Root cause of recurring "server won't start" / login-logo issues in Claude Code on the web: fresh containers need `pip install -r requirements.txt` and `PYTHONPATH=.` set before the app can import cleanly.
- Added `.claude/hooks/session-start.sh` (installs deps with `--ignore-installed` to dodge a Debian-managed `packaging` package conflict, sets `PYTHONPATH`, runs one smoke test) and registered it in `.claude/settings.json` under `SessionStart`.
- Validated: hook runs clean, full `pytest unit_tests/` suite passes, server starts and responds on `/api/ping`.

### 2026-09-06 — README rewritten twice
- First pass: expanded README into a long, fully-updated architecture doc (medallion, four-tab UI, deployment, troubleshooting) replacing the old CLI-only version.
- User asked for a ~1-page version instead — rewrote to ~115 lines covering both functional (4-tab workflow, features) and technical (medallion diagram, data flow, performance table) content concisely.

### 2026-09-06 — Critical regression audit and fix
- User reported the app "isn't working anymore, not even functionality from earlier commits." Audited every commit between the last main→develop sync (`b4d3433`) and HEAD.
- **Root cause found:** commit `821f52e` ("Implement server-side session management") introduced `self.ui_dir` references in `_route_clean_ui_path()` for the `/`, `""`, `/login` routes, but `MapperHandler` never sets `self.ui_dir` as an instance attribute (only receives `ui_dir` as a closure parameter to `make_handler()`). Every request to the login page crashed the handler's `__init__` with `AttributeError`, returning an empty/reset connection — **the entire app was unreachable from the login page onward**, which is why nothing downstream (mapper, templates, reporting) could be exercised either.
- **Second regression found:** commit `44f347d` changed expired/invalid-session API responses from a clean `401` JSON body to a `302` redirect to `/login`. Since `fetch()` follows redirects transparently, frontend code awaiting `response.json()` would instead receive the login page's HTML and fail with a cryptic parse error instead of the intended "session expired" message.
- **Fix (commit `9e98bd2`):** restored `ui_dir` (closure variable) references for the login route; reverted both session-check call sites (GET and POST dispatch) to return `401 {"error": "Session expired. Please login again."}` instead of a redirect. Verified end-to-end manually: `/` now serves login.html (200), `POST /api/login` sets a session cookie, `/app` and `/api/*` succeed with the cookie and correctly 401/302 (page routes) or 401 (API routes) without one. Full 135-test suite still green.
- Also audited the brand-management-modal commit (`996e727`) for a suspected duplicate-listener conflict on `#brandSelect` — turned out to be a false alarm: `setupBrandDropdownListeners()` (in `reporting.js`) targets the *Reporting* tab's brand filter elements, a completely different `#reportMainBrandSelect`, not the Mapper tab's `#brandSelect`. No actual conflict found there.

## Open Items / Things to Watch

- No live BigQuery access in this sandbox — all verification here is against mocked tests plus manual HTTP-level smoke tests of the running server. The user should re-verify end-to-end (login → mapper → reporting) with real BigQuery credentials.
- If "app not working" reports recur, check for a fresh `self.<closure-var>` mistake in `make_handler()` first — it's an easy pattern to reintroduce since the outer function's local variables are easy to mistake for instance attributes inside the nested class.
