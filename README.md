# Competitive Whitespace Tool

Birdeye's Competitive Whitespace Tool is a no-code location platform with AI-assisted source mapping, validation, enrichment, review, and reporting.

## User Journey
Secure login -> choose brand/source -> parse and map -> save all records -> review rejected rows -> inspect competitive gaps and data quality.

## Source Coverage
CSV, Excel, JSON, XML, GET JSON APIs, and browser Python/Pyodide. Brands are independent from formats and can use different formats over time. Demos include Pizza Hut, Domino's JSON, Demo Restaurant Excel, Little Caesars GET JSON, Demo XML, and Demo PE Python.

## Platform
- Fast parse: up to 50 records for discovery.
- Full save: reloads and processes the complete source.
- Invalid rows: routed to review without blocking valid rows.
- Worldwide fuzzy enrichment for city/state/country and ZIP/coordinate validation.
- BigQuery authoritative warehouse with persistent SQLite WAL mirrors for fast startup/reporting.
- Background enrichment and silent reporting synchronization.

## Reporting
Responsive dashboard with primary/competitor filters, state/city distributions, active stores and locations, gap ZIPs, quality metrics, missing jurisdictions, and Leaflet map markers.

## Reliability
Sample reference data is immutable. ZIP readiness uses SQLite first and BigQuery fallback. Session failures and 401/403/404 responses return to login. Login is not blocked by ZIP loading; `Sync US ZIPs` is available inside the app.

## Current Gaps
Full filtered multi-sheet Excel export, ZIP freshness reconciliation, complete enrichment write-back to review rows, and authenticated browser smoke coverage remain to be completed.

## Start
```bash
.venv/bin/python -m whitespace_tool.cli workflow-ui --host 127.0.0.1 --port 8765
```
Open http://127.0.0.1:8765/.
