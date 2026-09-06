# Codex Working Notes

This is the practical handoff for the Competitive Whitespace prototype. Update it after meaningful behavior changes so future work starts from the current code, not from old branch assumptions.

## Current Branch And Git Rules

- Active development branch: `develop_new`.
- `feature_21` contains the Pyodide/demo work and was merged into `develop_new`.
- Do not commit unless the user explicitly asks.
- Do not include unrelated local changes such as `.env.example` unless requested.
- `run.sh` was intentionally removed; start with `python -m whitespace_tool workflow-ui`.

## What The App Does

The app starts at a secure login page, then provides one workflow UI with separate tabs for source mapping, review error listings, template library, and reporting. It accepts CSV, XLSX/XLS, JSON, XML, GET JSON API, and browser Pyodide Python sources. Source data is mapped into a common location model, validated, written to BigQuery bronze tables, and invalid rows are retained in `error_listings` for review.

## Important Separation Rules

### Brand versus source format

Brands and source formats are independent. A brand can use any source format over time. `source_type_id` belongs to a mapping/template/source workflow, not to the brand form. Existing legacy source type values may remain in old rows, but they must not drive UI locking or prevent a different format.

### Fast parse versus full save

- Initial parsing samples up to 50 records to discover headers, nested paths, and mapping suggestions.
- Small files are parsed completely when they contain fewer than 50 records.
- Saving a template/listing dataset reloads the complete source when only a sample was parsed.
- Progress and completion messages must use the actual batch total, not the sample size.

### Valid and invalid rows

Every processed row counts toward the processed total. Valid rows go to listings; invalid rows go to `error_listings`. Do not block a batch merely because some or all rows are invalid. The user-facing completion wording is `X records processed. Y need review.`

## Demo And Public URL Rules

- Demo public URLs are locked to their configured source and expose Edit URL when editing is intentionally requested.
- Switching source input modes must not clear a demo URL or its lock.
- Demo brands should resolve through the loaded brand list; never assign a config object as if it were a database brand.
- Current demos include Pizza Hut CSV, Global Hotels CSV, Demo Restaurant Excel, Domino's JSON, Little Caesars GET JSON, Demo XML, and Demo PE Brand Python.
- Demo XML uses `https://samplelib.com/xml/sample-5mb.xml`.
- Demo PE Brand code is stored at `config/demo_pe_brand_python.py`, served by `/api/demo-python/pe-brand`, and exposed with Load sample and Copy code controls.
- LA City is no longer a Python editor radio option.

## Python Editor

Python runs in browser Pyodide. The script must assign a JSON-compatible object or list to `result`. External browser `pyfetch` calls can fail because of CORS or remote server restrictions; use the server-backed Public URL flow for ordinary remote files. Empty or whitespace-only editor content falls back to the starter example.

## State And Navigation Expectations

- Refresh keeps the current page when the session and server launch are valid.
- A killed/restarted server invalidates the old session and sends the user to the root/login flow.
- Root shows the centered Go to Whitespace Tool entry screen and must not auto-login.
- Unknown public URLs use the not-found page.
- Login URL is `/login`, not a query-string mapper URL.
- Brand selection must survive switching source formats, input modes, and New/demo radio states. Only selecting Create New Brand or logging out/master deletion intentionally clears it.

## UI Conventions

- Action buttons use verb-ing text and an inline spinner while working: `Parsing`, `Saving Brand`, `Updating Brand`, `Signing in`, etc.
- Error/status messages have a dismiss cross icon.
- Existing brand editing opens a centered popup; new-brand creation reuses that popup. Source format is not a brand property and is hidden from both brand forms.
- Source Preview is a mapped tabular table with sample values. Data Model is a two-pane view: source fields on the left and target listings fields on the right, with green mapped indicators.
- Required mapping fields appear first. Auto-mapped selections use the light-red verification state.

## Backend And Performance

- `whitespace_tool/workflow_server.py` owns HTTP routes and orchestration.
- Source adapters live under `whitespace_tool/source_adapters/`.
- SQLite WAL cache mirrors hot ZIP, brand, reporting, and error-count data. It must persist across server restarts; only stale cache entries should be invalidated.
- BigQuery remains the fallback/source of truth for brands, ZIPs, and live reporting data.
- Keep expensive ZIP/brand/report loading out of the first login paint. Lazy-load secondary app data and preload only the lightweight first layer needed by the logged-in app.

## Verification Checklist

For mapper changes, check all source types and these paths: new brand, existing brand, demo brand, public URL, upload file, Parse, Source Preview, Data Model, Save, invalid-row review, template reload, and refresh. Run:

```bash
node --check ui/js/mapper.js
python -m py_compile whitespace_tool/workflow_server.py
git diff --check
pytest -q
```

For backend changes, restart the server on one stable port and smoke-test the real button flow, not only unit tests:

```bash
.venv/bin/python -m whitespace_tool.cli workflow-ui --host 127.0.0.1 --port 8765
```

## Known Risk Patterns

- Do not duplicate event handlers in inline HTML and module JS.
- Do not use `selectedBrand` config objects where a loaded brand with `business_id` is required.
- Do not let source-specific reset helpers clear brand state.
- Do not validate mapped fields case-sensitively when CSV/Excel headers differ only by case or punctuation.
- Do not use sample row count as the save row count.
- Do not hide a required demo/source radio by forgetting to add it to `updateSourceVisibility()`.

## Documentation Maintenance

Update this file, `docs/assumptions_and_gaps.md`, and the relevant README section whenever a source type, URL, cache layer, route, validation rule, or navigation contract changes. Record unresolved behavior as a gap instead of silently treating it as complete.
