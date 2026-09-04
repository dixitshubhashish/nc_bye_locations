# Competitive Whitespace Prototype

Python-only prototype for Birdeye's competitive whitespace assessment. It separates source-specific acquisition from a unified restaurant/location model, stages/pushes unified BigQuery tables, and produces ZIP-level whitespace candidates.

Known assumptions and gaps are tracked in `docs/assumptions_and_gaps.md`.

## Run

```bash
.venv/bin/python -m whitespace_tool analyze --config config/demo.json --output-dir outputs/demo
.venv/bin/python -m whitespace_tool quality-check --config config/demo.json --output-dir outputs/demo
.venv/bin/python -m whitespace_tool push-bigquery --config config/demo.json --stage-dir outputs/bigquery --dry-run
```

Fetch the first-module ZIP base table from BigQuery public data:

```bash
.venv/bin/python -m whitespace_tool fetch-public-zips --config config/connections/storage.json --output data/source_files/us_zips_bigquery.csv
```

Current tested fetch result: 33,791 ZIP geography rows. Known missing ACS fields from the public join are surfaced by quality checks: 868 rows missing population, 1,348 missing median age, and 2,948 missing median household income. The generated full CSV is optional export/debug output; analysis reads ZIP demographics from BigQuery.

Launch the local workflow-template UI for adding a new brand source:

```bash
.venv/bin/python -m whitespace_tool workflow-ui
```

Open `http://127.0.0.1:8765/`, then choose `Go to Whitespace Tool`. Upload a source, map source columns/paths to the generic target fields, then choose `Save`. The server validates required mappings, stores the workflow template, and writes bronze rows.

Mapper requests and BigQuery failures are recorded in the daily rotating `logs/mapper.log` file. Save errors include a request ID in the UI response so the matching traceback can be found in that log. Set `MAPPER_LOG_DIR` to change the log directory.

The Workflow Templates view includes `Clear Saved Data`, a destructive action that requires confirmation. It soft-deletes user-entered business/listing/rejected data by setting `is_deleted` and `deleted_on`, while preserving `us_zipcodes`, `field_catalog`, `source_types`, and `workflow_templates`; it does not delete the dataset itself, and every action is logged.

Every parsed source type (CSV, Excel, JSON, XML, and GET API JSON) uses the shared validators in `whitespace_tool/data_validation/`. Rows with invalid mapped types or missing mandatory location values are written to `error_listings`; valid rows are written to the bronze location tables.

The medallion datasets are `birdeye_bronze_listings`, `birdeye_silver_listings`, and `birdeye_gold_listings`. The current mapper writes only to the bronze dataset.

Supported mapper inputs:


- CSV
- Excel `.xlsx`
- Excel `.xls`
- JSON
- XML
- GET API with JSON response
- Python Editor

Each input type is handled by a separate Python adapter under `whitespace_tool/source_adapters/`. Excel files expose sheet names in the UI so the user can choose which source to use.

The Workflow Templates screen also includes predefined templates for Domino's, Pizza Hut, and Little Caesars. These load known mapping templates into the mapper so each brand workflow can be solved and validated one at a time.

## Key System Enhancements & Architecture Features

### 1. High-Performance SQLite Sidecar Cache (`sqlite_cache.py`)
- Integrated a WAL-mode SQLite local cache (`data/cache/whitespace_cache.db`) for high-frequency queries (ZIP geography, brand lists, reporting summaries).
- Reduces repeat query latency from ~13.5 seconds to sub-millisecond execution (<1ms - 3.4ms).
- Invalidates reporting caches automatically whenever new listings or workflows are saved.

### 2. BigQuery Partitioning & Clustering
- `listings`, `error_listings`, and `listings_enriched` tables are partitioned daily by `ingested_at` (`DAY` partition).
- Clustered by `(state_code, zip_code, business_id)` to optimize geographic filtering and whitespace analytical queries.
- Restored `source_types` BigQuery table schema and seed records to support seamless template saving and metadata tracking.

### 3. Lightweight Instant Login Status Ping (`/api/ping`)
- Introduced a minimal `/api/ping` endpoint returning rapid JSON health status in `<1ms`.
- Prevents UI delays during initial load, immediately transitioning authentication status to **GREEN (`ready`)**.

### 4. Custom Field Validation & Duplicate Guard
- Added normalized token-matching validation in custom field creation (`create_custom_field`).
- Blocks duplicate standard or custom fields (e.g. attempting to re-add `address` as a custom field returns an informative HTTP 400 error).

### 5. Explicit Source Mapping Lifecycle & Visual Feedback
- Auto-mapping logic triggers cleanly upon clicking **Parse Source** rather than on initial file selection.
- Auto-mapped dropdown fields are highlighted in light red (`select.auto-mapped`) for visual verification.
- Re-mapping an already mapped source field prompts confirmation (`window.confirm`) to prevent accidental overwrites.

### 6. UI Refinements & Desktop Optimization
- Standardized action buttons (e.g., `Save Template and Listing Data`).
- Enforced clean URL routing without parameter pollution (`?fresh=1`).
- Added responsive styling tailored for laptop screens (`min-width: 1280px`).

Domino's can be explored through the unofficial first-party store locator endpoint used by community wrappers. The fetcher scans a ZIP list, caches raw ZIP responses with pickle, deduplicates by store ID, and writes mapper-ready JSON under a `Stores` array:

```bash
.venv/bin/python -m whitespace_tool fetch-dominos --zip-file data/source_files/us_zips.txt --output outputs/dominos_store_locator.json
```

This is not an official Domino's public API, so failures or schema changes should be treated as source-quality signals rather than silently trusted.

The Python Editor runs user-authored Python in a browser Pyodide runtime. Scripts may import standard-library modules and supported Pyodide packages, and can fetch or transform data as needed. Assign the final JSON-compatible object or list to `result`; that value is validated and passed into the same mapping workflow as every other source. The server receives only the resulting JSON and does not execute the script.

The demo config uses small sample files for brand locations only. ZIP geography and demographics are read from BigQuery public datasets.

For a current/realtime-oriented run, start from `config/live_bigquery.json`. It keeps ZIP demographics in BigQuery, requires live location sources where available, and marks snapshot sources so quality checks surface staleness instead of silently treating old extracts as current.

```bash
python3 -m whitespace_tool quality-check --config config/live_bigquery.json --output-dir outputs/live
python3 -m whitespace_tool analyze --config config/live_bigquery.json --output-dir outputs/live
```

To push directly to BigQuery, install `google-cloud-bigquery`, authenticate with Google Application Default Credentials, then run the same `push-bigquery` command without `--dry-run`.

To test the Birdeye BigQuery connection with a service account JSON:

```bash
cp config/connections/storage.example.json config/connections/storage.json
python3 -m pip install google-cloud-bigquery google-auth
python3 scripts/test_storage_connection.py
```

Put the downloaded service account file at `config/connections/keen-device-610-2af9b27dfda3.json`, or edit `credentials_json` in `config/connections/storage.json`. That local config and credential file are ignored by git.

`config/live_bigquery.json` uses a `demographics_source` of type `bigquery` and the configured bronze dataset. If you are not using Application Default Credentials, set `credentials_json` in `config/connections/storage.json` or pass `--credentials-json` when pushing warehouse tables.

## Configuration And Render Deployment

Local secrets are not committed. The app can read storage settings from either ignored `config/connections/storage.json`, a local ignored `.env`, or host environment variables. Start from:

```bash
cp .env.example .env
```

Environment variables supported by the app:

- `WORKFLOW_LOGIN_USER`
- `WORKFLOW_LOGIN_PASSWORD`
- `WORKFLOW_CONFIG`
- `BIGQUERY_PROJECT_ID` or `GOOGLE_CLOUD_PROJECT`
- `BIGQUERY_BRONZE_DATASET_ID`
- `BIGQUERY_SILVER_DATASET_ID`
- `BIGQUERY_GOLD_DATASET_ID`
- `GOOGLE_APPLICATION_CREDENTIALS` for a local service-account file path
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` for hosted deploys where the full service-account JSON is stored as a secret
- `REPORTING_LISTINGS_TABLE` to point the Reporting tab at a BigQuery table or view. If omitted, it reads raw bronze `listings`.

The Reporting tab is built in the app, not embedded from an external dashboard. It summarizes location counts by brand, state, county, city, and ZIP, supports multi-select main/competitor brand filters, and maps gaps where competitor brands are present but selected main brands are absent. Keep `REPORTING_LISTINGS_TABLE` on the bronze `listings` table for raw reporting, or point it to a BigQuery silver/gold view once you add transformation views.

For Render, create a Web Service from GitHub and use the workflow UI:

```bash
Build Command: pip install -r requirements.txt
Start Command: python -m whitespace_tool workflow-ui --host 0.0.0.0
```

The workflow UI includes source mapping, rejected-record review, template library, and the native Reporting tab. The server automatically uses Render's `PORT` environment variable. Add the environment variables above in Render's dashboard; paste the full BigQuery service account JSON into `GOOGLE_APPLICATION_CREDENTIALS_JSON` instead of committing a credential file. Do not upload or commit `.env`; Render stores these values as encrypted service environment variables.

This repo also includes `render.yaml`, so Render can pre-fill the build/start commands and prompt for secret environment variables.

## Approach

1. Fetch ZIP/ZCTA geography and demographics from BigQuery public data into the unified `us_zipcodes` shape. The current join uses `bigquery-public-data.geo_us_boundaries.zip_codes` for city/county/state/lat/lon and `bigquery-public-data.census_bureau_acs.zip_codes_2018_5yr` for population, income, age, poverty, labor, and housing fields.
2. Keep one source file per brand shape, with source freshness declared in config:
   - `whitespace_tool/sources/dominos_api.py` for a Domino's API JSON response.
   - `whitespace_tool/sources/pizza_hut_kaggle.py` for a Kaggle-style Pizza Hut CSV.
   - `whitespace_tool/sources/little_caesars_json.py` for Little Caesars JSON objects.
3. Use workflow template JSON files in `config/workflow_templates/` to translate each source into the internal schema. Adding a field or changing a source column should be a template edit, not analysis rewrites.
4. Run all data quality checks through `whitespace_tool/data_quality.py`: brand coverage, duplicate source keys, required fields, ZIP validity, ZIP-to-demographic joins, missing demographic metrics, coordinate sanity, source tier, sample-file usage, and stale `observed_at` timestamps.
5. Push unified tables to BigQuery using `whitespace_tool/warehouse_bigquery.py`. Bronze DDL is in `database/bronze_schema.sql`; load-ready JSONL and schema files are written to `outputs/bigquery/` during dry runs.
6. Run whitespace analysis from config. The current demo defines similar population profile as z-score distance over `population` and `median_age`; this lives in `config/demo.json`.

## Outputs

`outputs/demo/brand_locations.csv` contains Domino's, Pizza Hut, and Little Caesars records with ZIP demographics attached.

`outputs/demo/whitespace_zips.csv` contains ZIPs similar to Domino's ZIPs where Domino's is absent. It separates `competitor_present` from `no_tracked_brand_present` and includes median household income plus median age as the extra data point. Median age helps distinguish family/college/retiree trade areas that may have similar population totals but different demand patterns.

`outputs/demo/run_manifest.json` records config, sources, limitations, and summary counts.

`outputs/demo/data_quality_report.json` records the pass/fail result, source counts, brand counts, and issue details.

`outputs/bigquery/` contains one JSONL file per unified BigQuery table plus matching schema JSON files.

## Data Quality Notes

The sample data is not authoritative; it exists to demonstrate architecture. For submission quality, I would pull Domino's from the store API, Pizza Hut from the freshest available public extract or locator-derived source, and Little Caesars from current JSON source objects, then compare counts by state/ZIP against each brand's public locator or another reference. Raw payloads are preserved in `source_observations` so every normalized restaurant can be traced back to its source and observed timestamp.

Known gaps: no address geocoding, no fuzzy duplicate resolution across conflicting source IDs, no incremental diff report yet, and no real review ingestion. The schema reserves `reviews`, `analysis_runs`, and `whitespace_candidates` for those next steps.

