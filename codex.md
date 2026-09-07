# Codex Project Handoff

## Product
Competitive Whitespace Tool: secure login, source mapping, validation/review, templates, enrichment, and US location reporting.

## Rules
- Active branch: `develop_new`.
- Do not commit or push unless explicitly requested.
- `run.sh` is removed. Start with `.venv/bin/python -m whitespace_tool.cli workflow-ui --host 127.0.0.1 --port 8765`.
- Preserve unrelated user changes. Ignore `implementation_plan.md` when reconstructing current behavior.

## Data Flow
Parse samples up to 50 records for discovery; save reloads and processes the complete source. Valid rows are stored and invalid rows remain in Review Error Listings. Background enrichment uses the worldwide city reference for fuzzy location matching and ZIP/coordinate validation.

BigQuery is authoritative. Persistent WAL SQLite mirrors ZIPs, brands, reporting rows, query results, and error counters for fast startup. ZIP readiness checks SQLite first, falls back to BigQuery, and repopulates the mirror. ZIP readiness does not block login; the app provides `Sync US ZIPs` for readiness and retry.

## UI Contracts
Root is the centered entry page; `/login` is the secure login page. Session failures and 401/403/404 responses return to login. Login may show ZIP loading status but remains usable. Brands and formats are independent. Demo URLs remain locked with Edit URL support. Required mapping fields appear first; auto-mapped fields use light-red verification. Source Preview is tabular with values; Data Model is a green-indicator two-pane view.

Action buttons use verb-ing labels and spinners. Warnings/errors have dismiss controls. Reporting filters include primary, `~`-joined competitors, geography, and demographics; the primary brand is excluded from competitors. Reporting uses responsive full-width layout, spaced tables, full state labels, and orange gap-ZIP markers.

## Reporting And Enrichment
Reporting metrics include states, ZIPs, active brands/stores/locations, distributions, comparisons, gaps, missing jurisdictions, data quality, and map data. Dashboard payloads may be display-limited for responsiveness; mirrors retain full source rows. Reporting refresh on load is silent; explicit refresh shows progress. Enrichment runs in background batches and refreshes reporting mirrors.

## Verification
```bash
node --check ui/js/mapper.js
node --check ui/js/reporting.js
node --check ui/js/login.js
python3 -m py_compile whitespace_tool/workflow_server.py whitespace_tool/sqlite_cache.py
git diff --check
```

## Gaps
- Full filtered Excel export with separate location, metrics, gaps, distributions, and quality sheets.
- Explicit ZIP mirror freshness/TTL reconciliation after manual warehouse changes.
- Guaranteed high-confidence enrichment write-back to original review rows.
- Authenticated browser smoke coverage for all buttons and formats.
