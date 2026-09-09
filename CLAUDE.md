# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Competitive Whitespace Tool (Birdeye): a no-code location platform for competitive whitespace analysis — secure login, AI-assisted source mapping, validation/review, templates, worldwide geo enrichment, and reporting. User journey: login -> choose brand/source -> parse and map -> save all records -> review rejected rows -> inspect competitive gaps and data quality.

There is a project handoff doc, `codex.md`, maintained by prior agent sessions — read it for current in-flight work, watch items, and open gaps before making changes. **Update `codex.md` when making plans, completing changes, or noting new watch items** (this is an existing project convention, not new).

## Commands

Run the app locally:
```bash
.venv/bin/python -m whitespace_tool.cli workflow-ui --host 127.0.0.1 --port 8765
```
Open http://127.0.0.1:8765/. Install `requirements.txt` first for a clean environment. `run.sh` was removed — always start via the CLI module above (or `python -m whitespace_tool workflow-ui --host 0.0.0.0`, used in `Procfile` for deployment).

Other CLI subcommands (`whitespace_tool/cli.py`): `analyze`, `fetch-public-zips`, `quality-check`, `push-bigquery`, `fetch-dominos`.

Run tests:
```bash
python3 -m pytest                          # full suite (192 tests, unit_tests/)
python3 -m pytest unit_tests/test_geo_enrichment.py       # single file
python3 -m pytest unit_tests/test_geo_enrichment.py::SomeTestClass::test_name   # single test
```

Pre-commit verification (also listed in `codex.md`, keep both in sync):
```bash
node --check ui/js/mapper.js
node --check ui/js/reporting.js
node --check ui/js/review.js
node --check ui/reporting-tabs.js
node --check ui/js/login.js
python3 -m py_compile whitespace_tool/workflow_server.py whitespace_tool/sqlite_cache.py
python3 -m py_compile whitespace_tool/geo_enrichment.py whitespace_tool/warehouse_bigquery.py
git diff --check
```

There is no bundler/build step for the UI — `ui/*.js` and `ui/*.html` are served directly; `node --check` is syntax-only validation.

Environment: copy `.env.example` to `.env`. Key vars: `WORKFLOW_LOGIN_USER`/`WORKFLOW_LOGIN_PASSWORD` (app login), `WORKFLOW_CONFIG` (points at `config/demo.json`), `BIGQUERY_PROJECT_ID` + `BIGQUERY_{BRONZE,SILVER,GOLD}_DATASET_ID`, and either `GOOGLE_APPLICATION_CREDENTIALS` (local service-account JSON path) or `GOOGLE_APPLICATION_CREDENTIALS_JSON` (inline JSON, used on Render).

## Architecture

**`whitespace_tool/workflow_server.py`** is the monolithic core: HTTP routing, auth, source parsing orchestration, BigQuery orchestration, sample load/clear, review repair, reporting endpoints, and background jobs all live here. When making backend changes, this is almost always the file to start in. (Backend module extraction — splitting parsing/brand-template/reporting/enrichment-queue concerns out of this file — is a known, not-yet-done gap; see `codex.md` "Remaining Gaps".)

**Medallion data architecture on BigQuery** (authoritative warehouse):
- Bronze: raw parsed source rows.
- Silver: enriched/deduped reference layer, built by `build_silver_layer()` in `workflow_server.py` (e.g. the unified US ZIP reference is a union of canonical `us_zipcodes` + US rows from worldwide cities, deduped by ZIP with canonical winning).
- Gold: reporting-ready views/mirrors.
- Schema is defined in `whitespace_tool/warehouse_bigquery.py` (`TABLE_SCHEMAS`, `TABLE_CLUSTER_SPECS`) — **treat this as the live schema source of truth**; older raw `.sql` files under the repo may lag behind it.

**SQLite is a persistent performance mirror, not the edit authority.** It lives at `.cache/whitespace_cache.db` (WAL mode) and is defined in `whitespace_tool/sqlite_cache.py`. It mirrors US ZIPs, worldwide cities, query payloads, field catalogs, gold reporting locations, ZIP-brand activity, businesses, review counts, ZIP readiness, auto-repair stats, the enrichment queue, and quality listings. Reads check SQLite first, fall back to BigQuery, and repopulate the mirror; user edits and warehouse writes remain authoritative upstream. Display/pagination limits in the UI are presentation-only — mirrored source rows are never truncated by them.

**Geo enrichment** lives in `whitespace_tool/geo_enrichment.py`: normalizes state/city text, detects inverted coordinates, uses cached US ZIP/city data for US hierarchy repair, uses cached worldwide cities for country-level repair, and snaps offshore/ocean coordinates to the nearest reference city when a reliable nearby point exists. Coordinate repair is done via indexed SQLite lookups (not BigQuery spatial joins) for performance.

**Background jobs**: reference-data loading, silent reporting sync, and automatic review repair all run in background threads/batches. Auto-repair uses a persisted SQLite enrichment queue: it seeds a base set from current invalid records, claims a small batch (10 records/cycle), moves unresolved rows into a failed set, and swaps failed back into base once the current set is exhausted — this avoids retrying the same rows forever while still prioritizing user-driven requests. Background BigQuery work reuses a single `bigquery.Client` per worker lifecycle (avoid creating new clients per batch — this caused a prior gRPC socket/OOM leak, see `codex.md`).

**Frontend** (`ui/`) is modular, framework-free JS: `js/mapper.js` (source mapping/parse/save/data controls), `js/review.js` (rejected-row review/reprocess), `js/templates.js` (brand templates), `js/reporting.js` + `reporting-tabs.js` (dashboard, quality tab, charts), `js/common.js` (shared login/session/nav helpers), plus `login.html`/`login-hotfix.js` for the login page and `integrations.html` for the main app shell. Routing model: `/` is the centered entry page, `/login` is the secure login route, `/app` is the authenticated workspace (views selected via `?view=` query param: `mapperView`, `reportingView`, `reviewView`, `templateLibraryView`). Session failures and 401/403/404 responses redirect back to login.

**Source adapters** (`whitespace_tool/source_adapters/`, `sources/`) keep brand and source format independent — a brand can change formats (CSV, Excel, JSON, XML, GET JSON API, browser Python/Pyodide) over time without re-mapping logic changes. Demo brands/configs are in `config/demo.json` and `config/predefined_brand_templates.json`; field mapping definitions are in `config/field_registry.json`.

**Data flow contract**: parse samples inspect at most 50 records for discovery; save reloads and processes the complete source. Valid rows are stored; invalid rows are routed to Review Error Listings without blocking valid rows.

## Testing notes

`unit_tests/` mirrors much of the `whitespace_tool/` package structure (`analytics/`, `common/`, `mapping/`, `persistence/`, `reporting/`, `source_adapters/`, `sources/`, `system/`) plus top-level test modules for silver/gold layer building, warehouse schema, geo enrichment, memory-leak/heap stability (`test_memory_leak.py`, using `tracemalloc`), scheduler behavior, and mapping-layout UI contracts. When touching BigQuery-facing code, check `test_warehouse_schema.py` and `test_silver_enrichment.py`; when touching the SQLite mirror or reporting cache, check `test_reporting_cache.py` and `test_gold_mirror.py`.

The broader smoke-test matrix, fresh-upload fixture requirements, and presentation walkthrough live in `docs/smoke_test_and_presentation.md` — consult it before/after larger changes rather than duplicating that checklist here.

## Session Summary (2026-09-09)

The project is at/near code closure for the Birdeye "Stand and Deliver" assessment, on branch `develop_new`. `codex.md`'s "Remaining Gaps" section (numbered batches, each one dated and itemized) is the authoritative, detailed log of what's done vs. open — read it before starting new work. Standing rules for this phase: don't hallucinate/assume, don't run the full test suite unless asked (targeted files only), don't commit, restart the server after any backend `.py` change, keep `codex.md` current after every batch of work, and flag genuinely ambiguous product decisions (e.g. conflicting metric definitions) rather than guessing at them.

Major features/fixes landed this session (full detail in `codex.md`'s Sixth/Seventh/Eighth batches): a field-mapping confidence-scoring system (`field_mapping_confidence` table, adaptive suggestion ranking in `learn_mappings()`); a critical gold-mirror data-wipe guard in `sync_gold_mirror()`; out-of-US coordinate handling (worldwide-enrich-first, explicit "Save as Non-US Data" action, counted under AI Fixed); reporting sidebar filter styling unified + type-to-search added to geographic/competitor filters; Job History "Show More" turned into a real paginated popup; randomised (not sorted) claiming in the enrichment queue so "Fix with AI" spreads across brands instead of favoring one; auto-repair now backs off for ~10s after any real user action instead of competing with foreground requests; the save-progress loader is now dismissible with a background Job History status row and a completion dialog naming brand/source type/counts.

Deliberately left open, flagged rather than guessed at: a number-cards 4-way AI/Manual Fixed/Pending split + field-group pivot (blocked on an ambiguous `is_ai_enriched` semantic already flagged separately, and on a live-computation cost concern); external brand-identity enrichment via open data (email/phone/website); an app-wide messaging/copy tone audit; a pre-existing `save_mapper()` `bad_row_index` batch-reject bug that predates this session (test `test_save_mapper_routes_bad_rows_to_error_listings_without_halting_valid_rows` documents the gap) and needs a product decision before fixing.
