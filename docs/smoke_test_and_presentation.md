# Smoke Test And Presentation Reference

This is the compact operational and presentation reference for the Competitive Whitespace Tool. Update the result table whenever a source, route, or demo configuration changes.

## Product Story

The tool turns messy location sources into a reusable competitive whitespace analysis. A user can upload or reference CSV, Excel, JSON, XML, GET JSON, or Python connector data; map fields into a shared location model; save the complete source; review invalid records; enrich geographic values; and compare a primary brand with competitors across ZIPs, states, cities, demographics, and data quality.

The demonstration is configurable in `config/demo.json`. Similarity is defined by configured demographic metrics, currently population and median age; median household income is carried as an additional output metric. Brand/source format independence is intentional.

## Smoke Matrix

| Area | Check | Result | Evidence |
|---|---|---|---|
| Static UI | Root, login, and app pages serve | PASS | HTTP 200 on `/`, `/login`, `/app` |
| Routing | Unknown route returns not-found response | PASS | HTTP 404 on `/does-not-exist` |
| Login | Admin login with `bn` password alias | PASS | HTTP 200 on `/api/login` |
| Session | Authenticated session endpoint | PASS | HTTP 200 on `/api/session` |
| Brand bootstrap | Brand list route | PASS | HTTP 200 on `/api/brands` |
| Source registry | Source-type bootstrap | BLOCKED | Remote warehouse call exceeded 15 seconds on a fresh server |
| Source parsing | CSV, JSON, XML previews and nested fields | PASS | Covered by unit tests |
| Excel parsing | XLSX/XLS sheet discovery and preview | PASS | Covered by adapter tests |
| Full save behavior | Parse sample limit does not limit saved rows | PASS | Save-guard and source workflow tests |
| Invalid rows | Bad rows move to review flow | PASS | Validation and error-count tests |
| Geo enrichment | City/state/country/ZIP hierarchy and coordinate repair | PASS | Geo enrichment tests |
| Reporting cache | Mirror-first payload and refresh behavior | PASS | Reporting cache and mirror tests |
| Sample clearing | Local cleanup and warehouse soft-delete path | PASS | Sample and clear-data tests |
| Background repair | Queue, batch claims, retry/swap behavior | PASS | Scheduler tests |
| Full automated suite | All repository unit tests | PASS | 158 passed in 2.41 seconds |
| CLI analysis | Demo analysis from clean system Python | BLOCKED | BigQuery client missing from system Python; install requirements/use `.venv` |
| Browser workflow | Real clicks, uploads, and responsive visual states | NOT RUN | Browser-control surface unavailable in this session |

## Fresh Upload Smoke Run

For every demo, use a new upload instead of relying on an existing saved brand:

1. Log in and open Mappings.
2. Choose or create a brand, then independently choose the source format.
3. Select `Upload File`, choose a fresh CSV/XLSX/JSON/XML fixture, and confirm the file name appears.
4. Click `Parse`; verify Source Preview contains values and Data Model shows the two-pane mapped view.
5. Map required fields first, then add optional fields that exist in the source.
6. Save and verify the complete source row count, not the fast-parse sample count of 50.
7. Confirm invalid rows appear in Review Error Listings and valid rows appear in Reporting.
8. Repeat with Upload URL, Public URL, and GET JSON where supported.

Minimum fixtures: a CSV with one missing ZIP and one malformed coordinate; a two-sheet Excel workbook; flat and nested JSON; repeated-element XML; and a GET JSON response with headers, parameters, and at least ten mapped fields.

## Five-Minute Presentation Flow

1. Parse a fresh upload and show source-independent mapping.
2. Show fast parsing versus complete saving and the invalid-row review queue.
3. Show geographic enrichment and the manual-review boundary.
4. Show the Location Intelligence & Whitespace tab: primary/competitor filters, locations, ZIP gaps, map, and configured similarity metrics.
5. Show Data Quality & Improvements: completeness, invalid reasons, affected brands/geographies, and automatic/manual improvement counters.
6. Close with source coverage, snapshot, deduplication, and remote-readiness limitations.

## Current Assessment Gaps

- `/api/source-types` still depends directly on the remote warehouse during bootstrap; a local source-type mirror or bounded fallback is needed for fast first paint.
- A clean system-Python startup does not have BigQuery dependencies even though `requirements.txt` declares them. Setup must install requirements before CLI/warehouse workflows are considered runnable.
- Browser-level authenticated smoke automation is still missing.
- Run-over-run snapshots and change reporting are not built.
- Full filtered multi-sheet Excel export needs final end-to-end verification.
- Cross-source store identity resolution remains weaker when IDs differ.
- Brand coverage is visible but not benchmarked against an external expected-store count.
- True metro-area geography is not yet a first-class filter.
- The active Python warehouse schema can be newer than the illustrative SQL files; schema generation and migration checks should remain release checks.

## Release Gate

Do not call a release fully smoke-tested until source-type bootstrap returns quickly from a cold local cache, browser flow has been exercised with fresh upload fixtures, and the listed gaps are either closed or explicitly accepted in the presentation.
