# Competitive Whitespace Prototype

Python-only prototype for Birdeye's competitive whitespace assessment. It separates source-specific acquisition from a unified restaurant/location model, stages/pushes unified BigQuery tables, and produces ZIP-level whitespace candidates.

Known assumptions and gaps are tracked in `docs/assumptions_and_gaps.md`.

## Quick start: run the app locally (Windows & macOS)

Requires **Python 3.10+**. Run every command from the repository root.

### 1. Create a virtual environment and install dependencies

**macOS / Linux (bash/zsh):**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> If PowerShell blocks the activation script, allow it for the current user once:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, then re-run
> `.venv\Scripts\Activate.ps1`. Alternatively use `.venv\Scripts\activate.bat` in cmd.exe.

Once the venv is activated, `python` refers to the venv interpreter on both
operating systems, so the remaining commands are identical.

### 2. Configure credentials (`.env`)

The app reads storage settings from a local, git-ignored `.env` file (see the
full variable list under [Configuration And Render Deployment](#configuration-and-render-deployment)).
Copy the template and fill in your values:

```bash
cp .env.example .env          # macOS / Linux
```

```powershell
Copy-Item .env.example .env   # Windows PowerShell
```

Set `BIGQUERY_PROJECT_ID` and provide credentials one of two ways:

- **Service-account file:** `GOOGLE_APPLICATION_CREDENTIALS=config/connections/your-key.json`, or
- **Inline JSON:** paste the full service-account key (as a single line) into
  `GOOGLE_APPLICATION_CREDENTIALS_JSON={...}`.

The Reporting tab needs a reachable BigQuery project to show data. Without
credentials the UI still starts and the Reporting tab renders its layout, but
data requests return a configuration error until `.env` is set.

### 3. Launch the workflow UI (includes the Reporting tab)

```bash
python -m whitespace_tool workflow-ui
```

Open <http://127.0.0.1:8765/>, click **Go to Login**, sign in (default user
`admin`; in dev mode any non-empty password works unless `WORKFLOW_LOGIN_PASSWORD`
is set), then open the **Reporting** tab. Change the address with
`--host 0.0.0.0 --port 8791` or the `PORT` environment variable.

To stop the server, press `Ctrl+C`. To leave the virtual environment, run
`deactivate`.

## Running Unit Tests

Run the complete suite of 123 unit tests across all 8 domain subpackages:

```bash
python -m unittest discover -s unit_tests
```

Or run tests for a specific domain subpackage:

```bash
python -m unittest unit_tests.common.test_storage_config
python -m unittest unit_tests.persistence.test_warehouse_schema
python -m unittest unit_tests.analytics.test_sample_data
```

## System Architecture & Modular Subpackages

### Backend (`whitespace_tool`) Subpackages
The backend is structured into clean, domain-driven subpackages following **SOLID principles** and the **Repository Pattern**:

- **`whitespace_tool/common/`**: Core models (`LocationRecord`, `ZipDemographics`), field normalization, file I/O, field registry, and storage config.
- **`whitespace_tool/persistence/`**: Repository layer encapsulating BigQuery warehouse access (`warehouse_bigquery.py`) and SQLite local caching (`sqlite_cache.py`).
- **`whitespace_tool/analytics/`**: Haversine distance, spatial deduplication, data quality assertions, and mapping auto-learning.
- **`whitespace_tool/auth/`**: User authentication services and `/api/login` controller routes.
- **`whitespace_tool/mapping/`**: Field catalog repository, source preview generation, ingestion pipelines, and mapping routes.
- **`whitespace_tool/review/`**: Error listing query repository, rejection reporting, and record reprocessing.
- **`whitespace_tool/templates/`**: Built-in brand templates and workflow template catalog repository.
- **`whitespace_tool/system/`**: Storage health probes, dataset resets, medallion ETL pipeline (Silver/Gold), and background scheduler.
- **`whitespace_tool/reporting/`**: Analytical reporting metrics, market share calculations, and geographic filters.
- **`whitespace_tool/source_adapters/`**: Modular file format adapters (CSV, Excel `.xlsx`/`.xls`, JSON/GeoJSON, XML, REST GET API, Python Editor).
- **`whitespace_tool/sources/`**: External brand and public geography connectors (Demographics, Domino's, US ZIPs).
- **`whitespace_tool/data_validation/`**: Shared source row and normalized location validation rules.
- **`whitespace_tool/server/`**: Modular HTTP server subpackage (`handler.py`, `runner.py`, `dispatcher.py`) encapsulating `MapperHandler`, static asset routing, and API endpoint dispatchers.
- **`whitespace_tool/facades/`**: Centralized backward-compatibility facade package re-exporting all domain modules and server entry points (`workflow_server.py`).

### Frontend UI (`ui/`) Subpackages
The frontend user interface is organized into corresponding domain subpackages containing their own HTML partials, CSS stylesheets, and JS script logic:

- **`ui/index.html`**: Default Single-Page Application (SPA) HTML shell loading subpackage partials asynchronously.
- **`ui/integrations.html`**: Forwarding redirect script to `index.html` for backward URL compatibility.
- **`ui/common/`**: `common.html`, `header.html`, `footer.html`, `common.css`, `common.js`, `constants.js`, `loader.js` (shared layout, navigation, overlays, DOM helpers).
- **`ui/auth/`**: `auth.html`, `auth.css`, `auth.js` (login modal, credential handling, session storage, `/api/login`).
- **`ui/mapping/`**: `mapping.html`, `mapping.css`, `mapping.js` (source parsing, field mapping, custom fields, draft save/restore, editor dialog, `/api/save`, `/api/preview`, `/api/brands`).
- **`ui/review/`**: `review.html`, `review.css`, `review.js` (rejected listings table, edit & retry record modal, `/api/rejected`, `/api/reprocess`).
- **`ui/templates/`**: `templates.html`, `templates.css`, `templates.js` (predefined templates, brand filters, template catalog, `/api/templates`, `/api/templates/save`).
- **`ui/system/`**: `system.html`, `system.css`, `system.js` (readiness ping, header status, dataset reset, `/api/ping`, `/api/prepare`, `/api/clear`).
- **`ui/reporting/`**: `reporting.html`, `reporting.css`, `reporting.core.js`, `reporting.tabs.js`, `reporting.wiring.js` (whitespace analytics, market share dashboard, geographic filters).
- **`ui/facades/`**: `constants.js`, `login-hotfix.js`, `common.js`, `mapper.js`, `review.js`, `templates.js` (centralized UI compatibility facade scripts).

### Backward-Compatibility Facades (`whitespace_tool/facades/` & `ui/facades/`)
To maintain zero breaking changes while enforcing complete subpackage decoupling:
- **Backend Facades (`whitespace_tool/facades/`)**: Centralized subpackage re-exporting all 13 backend modules (`analysis`, `cli`, `config`, `data_quality`, `field_registry`, `io`, `learning`, `models`, `normalization`, `sample_data`, `sqlite_cache`, `storage_config`, `warehouse_bigquery`). All internal backend files import directly from canonical subpackages (`whitespace_tool.common`, `whitespace_tool.persistence`, etc.).
- **Frontend Facades (`ui/facades/`)**: Centralized directory holding legacy polyfill scripts (`constants.js`, `login-hotfix.js`, `common.js`, `mapper.js`, `review.js`, `templates.js`) that inject or re-export subpackage components (`ui/common/`, `ui/auth/`, `ui/mapping/`, etc.).

### Reporting Data Connection & BigQuery Analytics Views Target
- **Responsible Connection File**: `whitespace_tool/workflow_server.py` (`reporting_summary()`, lines 2286–2370).
- **Active Data Target**: Direct connection to **BigQuery Analytics Views** (`gold.vw_zip_brand_activity`, `gold.vw_reporting_locations`, `gold.vw_reporting_gap_base`).
- **Preserved Fallback**: The local SQLite Gold Mirror (`location_cache.db`) check in `workflow_server.py` is preserved as a commented fallback option.
- **Detailed Data Architecture**: Complete flow diagrams, dataset schemas, and pipeline specifications are documented in [DATAFLOW.md](DATAFLOW.md).

Full architectural details, design rationale, and file-by-file inventories are documented in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and [WALKTHROUGH.md](WALKTHROUGH.md).

## Run (advanced CLI)

The virtual-environment setup above applies to these commands too; activate the
venv first, then use `python` (shown below as `.venv/bin/python` for an
unactivated macOS/Linux shell — on Windows use `.venv\Scripts\python`).

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
- Integrated a WAL-mode SQLite local cache (`.cache/whitespace_cache.db`) for high-frequency queries (ZIP geography, brand lists, reporting summaries).
- Reduces repeat query latency from ~13.5 seconds to sub-millisecond execution (<1ms - 3.4ms).
- Invalidates reporting caches automatically whenever new listings or workflows are saved.

### 2. BigQuery Partitioning & Clustering
- `listings` and `listings_enriched` are partitioned daily by `first_observed_at`; `error_listings` is partitioned daily by `observed_at`.
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
