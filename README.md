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
Sample reference data is immutable. ZIP readiness uses SQLite first and BigQuery fallback. Session failures and 401/403/404 responses return to login. Login is not blocked by ZIP loading; `Sync US ZIPs` is available inside the app.

SQLite is WAL-backed and persistent at `.cache/whitespace_cache.db`. It mirrors ZIP geography, worldwide cities, reporting locations, ZIP-brand activity, businesses, query payloads, and review counters. Reporting and ZIP readiness use the local mirror first, then refresh from the warehouse when needed. Display limits on maps and tables do not limit the mirrored source rows.

## Smoke And Presentation Reference
Use [docs/smoke_test_and_presentation.md](docs/smoke_test_and_presentation.md) for the smoke matrix, fresh-upload checklist, five-minute presentation flow, and current assessment gaps.

## Current Gaps
Cold-start source-type bootstrap still needs a fast local fallback when the warehouse is slow or unavailable. Authenticated browser-level smoke tests, run-over-run snapshots, external source coverage benchmarking, true metro definitions, cross-source identity matching, and final multi-sheet Excel export verification remain open.

## Start
```bash
.venv/bin/python -m whitespace_tool.cli workflow-ui --host 127.0.0.1 --port 8765
```
Open http://127.0.0.1:8765/.

For a clean environment, install `requirements.txt` before running the CLI. The current demonstration is US ZIP based; metro-area definitions and run-over-run snapshots are not yet first-class features.
