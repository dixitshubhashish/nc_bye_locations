# Current System Reference

The browser modules are `common.js` (routing/session/readiness), `mapper.js` (sources/mapping), `review.js` (rejected rows), `templates.js` (lazy templates), and `reporting.js` (metrics/filters/maps). `workflow_server.py` owns routes and orchestration; adapters and validators are separate backend modules.

Initial parsing samples at most 50 records. Saving reloads the full source. Every row is counted; valid rows persist and invalid rows go to review. Enrichment runs in small background batches against worldwide city data, then rebuilds reporting data.

SQLite `.cache/whitespace_cache.db` is WAL-backed and persistent. It mirrors ZIP geography, gold reporting locations, ZIP-brand activity, businesses, query payloads, and error counters. Reporting reads the mirror first and falls back to BigQuery when unavailable. ZIP startup follows the same mirror-first/fallback pattern; BigQuery remains authoritative for edits and sync. Login is not blocked by ZIP readiness; the in-app `Sync US ZIPs` control handles readiness.

Reporting covers state/ZIP totals, active brands/stores/locations, state/city distributions, competitor comparisons, gaps, missing jurisdictions, quality, and map records. The state KPI uses live data with a maximum of 50; ZIP totals use live distinct reference data without an arbitrary cap. Display limits for maps/tables do not limit mirrored source data.

Root leads to the centered entry screen and `/login` is the secure login route. Refresh preserves the active tab when the session is valid. 401/403/404 responses return to login. Internal storage layer names belong in code/logs, not upfront product messages.

## Open Gaps
1. Separate full filtered Excel export with multiple reporting sheets.
2. Durable ZIP freshness metadata and asynchronous reconciliation.
3. Complete fuzzy repair write-back into review rows.
4. Authenticated browser-level smoke tests.
