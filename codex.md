# Codex Project Handoff

## Product
Competitive Whitespace Tool: secure login, source mapping, validation/review, templates, enrichment, and US location reporting.

## Rules
- Active branch: `develop_new`.
- Do not commit or push unless explicitly requested.
- `run.sh` is removed. Start with `.venv/bin/python -m whitespace_tool.cli workflow-ui --host 127.0.0.1 --port 8765`.
- Preserve unrelated user changes. When auditing behavior, trust active code and tests first, then use docs as context.
- Current `develop_new` head: `44e4492 antigravity v4 stability: worldwide cachedb enrichment, mandatory country field and hierarchy resolution`.

## Data Flow
Parse samples up to 50 records for discovery; save reloads and processes the complete source. Valid rows are stored and invalid rows remain in Review Error Listings. Background enrichment uses the worldwide city reference for fuzzy location matching and ZIP/coordinate validation.

BigQuery is authoritative. Persistent WAL SQLite mirrors ZIPs, brands, reporting rows, query results, and error counters for fast startup. ZIP readiness checks SQLite first, falls back to BigQuery, and repopulates the mirror. ZIP readiness does not block login; the app provides `Sync US ZIPs` for readiness and retry.

The active warehouse schema is defined in `whitespace_tool/warehouse_bigquery.py`; older SQL files may lag behind it. Current generated schemas include listing enrichment flags (`validated`, `enriched_at`, `max_enriched`), `country_code`, `error_listings.is_ai_enriched`, and `quality_fix_events`.

Local SQLite mirrors are defined in `whitespace_tool/sqlite_cache.py` and currently cover US ZIPs, worldwide cities, query payloads, field catalogs, gold reporting locations, ZIP-brand activity, businesses, review counts, ZIP readiness, auto-repair stats, enrichment queue, and quality listings.

The mirror is persistent at `.cache/whitespace_cache.db` and uses WAL mode. It is a performance layer, not the edit authority: user edits and warehouse writes remain authoritative upstream, while background refresh repopulates local reporting and readiness data. Reporting/map/table display limits are presentation limits only; source rows remain mirrored separately.

## UI Contracts
Root is the centered entry page; `/login` is the secure login page. Session failures and 401/403/404 responses return to login. Login may show ZIP loading status but remains usable. Brands and formats are independent. Demo URLs remain locked with Edit URL support. Required mapping fields appear first; auto-mapped fields use light-red verification. Source Preview is tabular with values; Data Model is a green-indicator two-pane view.

Action buttons use verb-ing labels and spinners. Warnings/errors have dismiss controls. Reporting filters include primary, `~`-joined competitors, geography, and demographics; the primary brand is excluded from competitors. Reporting uses responsive full-width layout, spaced tables, full state labels, and orange gap-ZIP markers.

## Reporting And Enrichment
Reporting metrics include states, ZIPs, active brands/stores/locations, distributions, comparisons, gaps, missing jurisdictions, data quality, and map data. Dashboard payloads may be display-limited for responsiveness; mirrors retain full source rows. Reporting refresh on load is silent; explicit refresh shows progress. Enrichment runs in background batches and refreshes reporting mirrors.

The reporting quality tab is intentionally separate from the whitespace/location tab. It is backed by `error_listings`, fix counters, and local quality mirrors, and should describe invalid listings, unresolved issues, impacted brands/geographies, and automatic/manual improvement counts without exposing backend terms in the UI.

Automatic review repair uses a persisted SQLite enrichment queue. It seeds a base set from current invalid records, claims a very small batch, moves unresolved rows into a failed set, and swaps failed back into base when the current set is exhausted. This is intended to prevent retrying the same first rows forever while keeping user-driven requests higher priority.

Worldwide geo enrichment now lives in `whitespace_tool/geo_enrichment.py`. It normalizes state/city text, detects inverted coordinates, uses cached US ZIP/city data for US hierarchy repair, uses cached worldwide cities for country-level repair, and can snap offshore/ocean coordinates to the nearest reference city when a reliable nearby point exists.

## Verification
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

The short operational smoke checklist, fresh-upload fixture requirements, HTTP evidence, and presentation walkthrough are maintained in `docs/smoke_test_and_presentation.md`.

## Current Audit
- Architecture: `workflow_server.py` owns routing, auth, parsing, BigQuery orchestration, sample load/clear, review repair, reporting, and background jobs. The UI is modularized (`mapper.js`, `review.js`, `templates.js`, `reporting.js`, `reporting-tabs.js`, `common.js`).
- Assessment fit: source adapters are separated, brand/source format independence exists, demo config is present, invalid rows are visible, provenance timestamps/content hashes exist, and reporting covers whitespace plus quality. Run-over-run diffing remains an explicit gap.
- Latest delta & memory optimizations:
  - Fixed Render web service OOM memory leak: replaced unbounded 50,000-row fetches in `auto_repair_error_batch()` with targeted BigQuery queries filtered directly by claimed `(event_id, row_number)` keys via `_fetch_rejected_by_keys()`.
  - Reused a single `bigquery.Client` lifecycle instance throughout the entire `start_auto_repair()` background worker, eliminating leaking gRPC transport sockets and thread pools.
  - Increased repair batch size to 10 records per iteration (cutting loop iterations and overhead by 10x).
  - Added dedicated memory leak and heap stability test suite (`unit_tests/test_memory_leak.py`) tracking `tracemalloc` allocations and single-client assertions (192 total tests passing).
  - Refactored BigQuery silver SQL view to remove Cartesian $O(N \times M)$ `nearest_city` spatial subqueries, delegating coordinate repairs to indexed SQLite lookups in `whitespace_tool/geo_enrichment.py`.
- Watch item: mapping labels currently call listing `name` "Brand Name" in `config/field_registry.json` and `ui/js/mapper.js`, while the data model also has a separate business/brand. This can confuse users and should be reviewed before further mapper changes.
- Watch item: `config/predefined_brand_templates.json` still describes Little Caesars as JSON, while the interactive UI has GET JSON API demo behavior. Keep demo metadata and UI behavior aligned.
- Watch item: docs and generated Python schema are ahead of older SQL files. Treat `warehouse_bigquery.TABLE_SCHEMAS` as the live schema source unless the SQL files are regenerated.
- Watch item: quality metrics mix live review rows with fix counters. If a fixed row is soft-deleted from review, the visible denominator and fix counters must reconcile from `quality_fix_events`, not only the current active review population.

## Remaining Gaps
- Run-over-run change tracking needs snapshot history.
- Authenticated browser smoke coverage should exercise login, source demos, parse/save/review, reporting filters, sample load/clear, and logout.
- Backend module extraction is still needed around source parsing, brand/template management, reporting, and enrichment queues.
- Demo metadata should be reconciled so README/config/UI all describe the same current demos.
- The smoke matrix and PPT-ready walkthrough live in `docs/smoke_test_and_presentation.md`. The latest smoke run had 158 passing automated tests, HTTP 200 for root/login/app/session/brands, and a reproducible cold-start delay on `/api/source-types` when the remote warehouse path is required.
- A fresh upload smoke run must use new CSV, Excel, JSON, XML, GET JSON, and Python fixtures; parse may inspect at most 50 records, but save must verify the complete source count.
- Root serves the centered entry screen, `/login` is the secure route, and `/app` is the authenticated workspace. Refresh preserves the active view when the session remains valid; unauthorized and not-found flows return to login/not-found handling.
- The current reporting model supports US-wide, state, county, city, and ZIP analysis. It does not yet provide true metro-area boundaries or historical snapshot diffs.
