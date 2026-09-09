# Competitive Whitespace Tool

Birdeye's Competitive Whitespace Tool is a no-code location platform for competitive whitespace analysis, AI-assisted source mapping, validation, enrichment, review, and reporting.

## User Journey
Secure login -> choose brand/source -> parse and map -> save all records -> review rejected rows -> inspect competitive gaps and data quality.

## Source Coverage
CSV, Excel, JSON, XML, GET JSON APIs, and browser Python/Pyodide. Brands are independent from formats and can use different formats over time. Demos include Pizza Hut, Domino's JSON, Demo Restaurant Excel, Little Caesars GET JSON, Demo XML, and Demo PE Python.

## Platform
- Fast parse: up to 50 records for discovery.
- Full save: reloads and processes the complete source.
- Invalid rows: routed to review without blocking valid rows.
- Worldwide fuzzy enrichment for town/city/state/country, ZIP realignment, inverted coordinate repair, and nearest-city correction for offshore coordinates.
- BigQuery authoritative warehouse with persistent SQLite WAL mirrors for fast startup/reporting.
- Background enrichment and silent reporting synchronization.

## Reporting
Responsive dashboard with primary/competitor filters, state/city distributions, active stores and locations, gap ZIPs, quality metrics, completeness, duplicate/freshness signals, entity-resolution outcomes, historical comparisons, missing jurisdictions, and Leaflet map markers.

The demonstration definition lives in `config/demo.json`: Domino's is the subject brand, Pizza Hut and Little Caesars are competitors, and similar ZIPs are scored from configured demographic metrics such as population and median age. Median household income is carried as an additional business-useful output for whitespace prioritization.

## Reliability
Sample reference data is immutable. ZIP readiness uses SQLite first and BigQuery fallback. Session failures and 401/403/404 responses return to login. Login is not blocked by ZIP loading; `Sync US ZIPs` is available inside the app. Background review and auto-repair pipelines use targeted key queries, bounded batching (10 records/cycle), and reused client connection pools to prevent memory growth and socket leaks.

SQLite is WAL-backed and persistent at `.cache/whitespace_cache.db`. It mirrors ZIP geography, worldwide cities, reporting locations, ZIP-brand activity, businesses, query payloads, and review counters. Reporting and ZIP readiness use the local mirror first, then refresh from the warehouse when needed. Display limits on maps and tables do not limit the mirrored source rows. Automated tests (215 collected as of 2026-09-09) include unit tests, mapping layout contracts, geo-enrichment, and memory-leak verification; one pre-existing test is a known failure unrelated to feature work — see `codex.md` Remaining Gaps.

## Smoke And Presentation Reference
Use [docs/smoke_test_and_presentation.md](docs/smoke_test_and_presentation.md) for the smoke matrix, fresh-upload checklist, five-minute presentation flow, and current assessment gaps.

## Data Model Rules
Only `brand` is mandatory to accept a record, at every layer — field config, mapper validation, row acceptance, and the BigQuery schema itself. A record's brand is fixed by its `event_id -> business_id` relation once created; it cannot be changed by re-submitting a different brand string. Global (non-US) postal codes are preserved and upper-cased rather than digit-stripped.

Coordinates are repaired before they are judged: a longitude outside ±180 is folded back into range (a wrapped `-245.22` is really `114.78`, a real meridian), while an impossible latitude is flagged rather than silently folded to another hemisphere. Reverse-geocoding is capped at 50km when it *snaps automatically* and 100km when it *suggests a city for a person to confirm* — a silent repair earns less benefit of the doubt than one a human approves.

Source columns no typed field covers are preserved per row in `listings.custom_fields` and carried through silver, gold and the SQLite mirror, because every parse presents a different column list and a fixed schema can never anticipate them all. Values that cannot be what their column means (a phone reading `N/A`, a revenue reading `excellent`) are cleared and left for enrichment rather than stored as junk — geo fields are exempt, since `clean_zip`, `normalize_state_code` and the cached city↔ZIP lookups are smarter than a generic rule.

Every listing that was ever invalid stays counted. Fixing a record soft-deletes its error row, so the review totals are computed over both live and soft-deleted rows via `was_ever_invalid` / `resolution_status`, and split into five mutually exclusive states (AI fixed, fixed from an AI suggestion, fixed manually, AI suggestion pending, manual pending) that must sum to the total.

## Current Gaps
Cold-start source-type bootstrap still needs a fast local fallback when the warehouse is slow or unavailable. Authenticated browser-level smoke tests, run-over-run snapshots, external source coverage benchmarking, true metro definitions and cross-source identity matching remain open, as does deferred single-row re-validation (`user_reviewed` status). Test coverage sits at roughly half the codebase, concentrated in the HTTP layer.

Shipped since this section was last written, and no longer gaps: the hierarchy-resolution picker for conflicting ZIP vs. coordinate readings, the save-job history panel with pagination, duplicate-detection messaging on save, multi-sheet exports (now ZIP bundles carrying a workbook, normalized CSVs, a per-brand competitor sheet and a README naming the filters that produced them), and server-side session enforcement — login previously validated credentials but issued nothing, leaving every `/api/*` route open to an unauthenticated caller.

See `docs/bug_tracker.md` for live fixed-vs-open status and `codex.md` for the detailed batch history.

## Start
```bash
.venv/bin/python -m whitespace_tool.cli workflow-ui --host 127.0.0.1 --port 8765
```
Open http://127.0.0.1:8765/.

For a clean environment, install `requirements.txt` before running the CLI. The current demonstration is US ZIP based; metro-area definitions and run-over-run snapshots are not yet first-class features.
