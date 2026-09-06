# Competitive Whitespace Prototype

A web-based data platform for competitive whitespace assessment, combining restaurant/location data ingestion, quality validation, enrichment, and geographic analysis. The system separates source-specific acquisition from a unified data model, stages data through a medallion architecture (Bronze → Silver → Gold), and provides real-time reporting with data quality insights.

## Quick Start

### Prerequisites
- Python 3.9+
- Google Cloud BigQuery access (with service account credentials)
- Modern browser (Chrome/Firefox/Safari/Edge)

### Local Setup

```bash
# Clone and install dependencies
git clone https://github.com/dixitshubhashish/nc_bye_locations.git
cd nc_bye_locations
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your BigQuery project ID, dataset names, and credentials
```

**Environment Variables:**
- `WORKFLOW_LOGIN_USER` / `WORKFLOW_LOGIN_PASSWORD` - Web UI authentication
- `BIGQUERY_PROJECT_ID` or `GOOGLE_CLOUD_PROJECT` - GCP project
- `BIGQUERY_BRONZE_DATASET_ID` - Bronze (raw) dataset (default: `birdeye_bronze_listings`)
- `BIGQUERY_SILVER_DATASET_ID` - Silver (enriched) dataset (default: `birdeye_silver_listings`)
- `BIGQUERY_GOLD_DATASET_ID` - Gold (aggregated views) dataset (default: `birdeye_gold_listings`)
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to service account JSON (local)
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` - Full JSON (for Render/hosted deploys)

### Start the Application

```bash
python -m whitespace_tool workflow-ui --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/` and log in with credentials from `.env`.

## Application Architecture

### Web UI: Four-Tab Workflow

The application is organized as a four-step workflow for data ingestion, validation, and analysis:

#### 1. **Mapper Tab** (Data Source Ingestion)
- Upload location data from multiple sources:
  - **CSV** - Comma-separated values
  - **Excel** - `.xlsx` and `.xls` files with sheet selection
  - **JSON** - Structured or array-based JSON
  - **XML** - Hierarchical XML documents
  - **GET API** - JSON responses from HTTP endpoints
  - **Python Editor** - Custom transformation scripts (Pyodide runtime in browser)
  
- **Mapping Workflow:**
  1. Select source type and upload file
  2. Click "Parse Source" to auto-map columns
  3. Review mappings and adjust if needed (auto-mapped fields highlighted in red)
  4. Confirm required fields (name, address, zip_code, etc.)
  5. Click "Save Template and Listing Data"
  
- **Template System:**
  - Auto-save mappings as reusable templates for each source
  - Predefined templates for sample brands (Starlight Pizza, Crimson Slice, Pinnacle Pizza)
  - Edit templates in the Template Library tab
  - Templates stored in BigQuery for persistence

#### 2. **Review Error Listings Tab** (Quality Control)
- View rejected rows that failed validation
- Error breakdown by source type and issue category
- Per-brand error statistics with pie chart visualization
- Edit individual records:
  - Fix missing required fields (name, address, zip_code, phone)
  - Add optional fields (coordinates, ratings, hours, etc.)
  - See enrichment status and data completeness
  - Click "Reprocess" to revalidate and save
- Soft-delete corrupted records without losing audit trail

#### 3. **Template Library Tab** (Workflow Management)
- Search and manage all saved mapping templates
- View source field details and parsing rules
- Edit field mappings for existing templates
- Lazy-loaded pagination (100 templates initially, then 500/page on scroll)
- Template preview showing actual source data structure
- Copy/reuse templates across similar sources

#### 4. **Reporting Tab** (Analytics & Insights)
- **Multi-Brand Filter:**
  - Select main brands to analyze
  - Select competitor brands for comparison
  - Apply geographic filters (state, county, city, ZIP code)
  
- **Key Metrics:**
  - Location counts by brand
  - Data enrichment percentages (fully enriched, geo-enriched, ZIP-enriched, city-enriched)
  - Coordinate source distribution (listing coordinates vs. ZIP centroid vs. city centroid)
  - Data quality summary (coordinate/ZIP completeness, duplicate rate)
  - Gap analysis - ZIPs where competitors are present but main brands are absent
  
- **Interactive Map:**
  - Green pins: locations with full coordinates
  - Blue pins: ZIP-code only locations (using ZIP centroid)
  - Red pins: ZIP code not found/invalid
  - Click pins for location details
  
- **Sample Data Tables:**
  - Top states and cities by location count
  - Brands and their coverage statistics
  - ZIP code whitespace opportunities (sorted by population/income)

## Data Platform: Medallion Architecture

### Bronze Layer (Raw Data)
**BigQuery Dataset:** `birdeye_bronze_listings`

Raw, immutable data as ingested from sources:
- `businesses` - Business metadata (name, source_id, source_type)
- `listings` - Location records with user-entered data (address, coordinates, phone, hours, ratings)
- `error_listings` - Validation failures with error details and raw_record for recovery
- `workflow_templates` - Saved mapping configurations per source
- `field_catalog` - Available fields (standard + custom) for the UI
- `source_types` - Metadata about each source type (CSV, API, etc.)
- `us_zipcodes` - ZIP code geography and demographics (from BigQuery public data)

**Partitioning & Clustering:**
- `listings` and `listings_enriched`: partitioned daily by `first_observed_at`
- `error_listings`: partitioned daily by `observed_at`
- Clustered by `(state_code, zip_code, business_id)` for geographic queries

### Silver Layer (Validated & Enriched)
**BigQuery Table:** `birdeye_silver_listings`

Validated, deduplicated, and enriched location records:
- Coordinates enriched from ZIP code centroids and city/state centroids if missing
- Enrichment status tracked per record:
  - **fully_enriched** - Has coordinates AND name/phone/address filled
  - **geo_enriched** - Has coordinates (from listing or ZIP centroid)
  - **zip_enriched** - Uses ZIP code centroid as fallback
  - **city_enriched** - Uses city/state centroid as fallback
  - **minimal** - Only address/ZIP, no coordinates
- Coordinate source tracked (source_listing, zip_centroid, city_state_centroid)
- Last observed timestamp for staleness detection

**Refresh Strategy:**
- Built on-demand when stale cache is detected (manual click on "Refresh Reports")
- Built automatically on hourly schedule (runs at HH:00 via background thread)
- Uses `build_silver_layer()` which validates and enriches from bronze

### Gold Layer (Pre-Aggregated Views)
**BigQuery Dataset:** `birdeye_gold_listings`

Pre-computed aggregation views for sub-second reporting queries. All views read from `silver.listings_enriched` and `bronze.us_zipcodes`:

- **`vw_zip_brand_activity`** - Grain: (zip_code, brand_name)
  - Location count per ZIP per brand
  - City/state/county coordinates
  - Max last_observed_at for staleness detection
  
- **`vw_state_summary`** - Grain: (state_code, state_name, brand_name)
  - Location count, city count, ZIP count per state per brand
  
- **`vw_city_summary`** - Grain: (city_name, state_code, state_name, county, brand_name)
  - ZIP count and location count per city per brand
  
- **`vw_brand_summary`** - Grain: (brand_name)
  - Total locations, states, counties, cities, ZIPs per brand
  
- **`vw_listing_quality_summary`** - Overall data quality metrics
  - Total rows, rows with coordinates, rows with ZIP codes
  - Distinct (deduplicated) row counts
  - Last observed timestamp
  
- **`vw_geo_reference`** - Deduped geography (state/county/city combinations)
  - Supports filter dropdowns

**Refresh Strategy:**
- Built alongside silver on hourly schedule and on-demand refresh
- Simple views (non-materialized) that are "as fresh as the last silver build"
- Reports query gold views for aggregations; individual records use silver/bronze

### SQLite Mirror Cache (Local Sidecar)
**File:** `.cache/whitespace_cache.db`

High-performance local copy of gold layer pre-aggregations:
- Reduces reporting latency from ~13.5s to <1ms
- Stores denormalized copies of gold view results
- Automatically synced when silver/gold rebuild
- Falls back to BigQuery if cache is stale or missing
- Invalidated when:
  - New listings are saved
  - Error listings are reprocessed
  - Manual "Refresh Reports" clicked
  - Hourly scheduler rebuilds silver/gold

## Hourly Medallion Scheduler

Background thread (daemon) that runs continuously:
1. Every hour at HH:00:
   - Calls `build_silver_layer()` - validates and enriches bronze → silver
   - Calls `build_gold_layer()` - creates/updates pre-aggregated views
   - Calls `sync_gold_mirror()` - syncs gold views → SQLite cache
2. Logs refresh timestamp and any errors
3. Errors are logged but don't stop the loop; next hour's refresh proceeds independently

Reuses `REPORTING_REFRESH_LOCK` so hourly refresh and manual on-demand refresh never collide.

## Data Validation & Enrichment

### Validation Rules
Every row is validated through `whitespace_tool/data_validation/`:
- **Required:** name, address, zip_code, state_code, county
- **Type Checks:** Coordinates are numeric; phone matches patterns; dates parse
- **ZIP Validation:** ZIP code exists in `us_zipcodes` table
- **Deduplication:** Duplicate source IDs within same brand are flagged

Invalid rows → `error_listings` table with error details  
Valid rows → Bronze `listings` table → Silver enrichment

### Enrichment Pipeline
1. **Coordinate enrichment** (if coordinates missing):
   - Join `us_zipcodes` on zip_code to get ZIP centroid
   - Join city/state lookup to get city centroid as final fallback
   - Track which source was used (source_listing, zip_centroid, city_state_centroid)

2. **Data completeness tracking:**
   - Count rows by enrichment status (fully/geo/zip/city/minimal)
   - Calculate percentages (e.g., "82% fully enriched")
   - Track coordinate source distribution

3. **Deduplication:**
   - Group by normalized (brand, address, zip_code)
   - Keep latest observed record, archive older duplicates

## Sample Data & Testing

### Load Sample Dataset
Click "Load Sample Dataset" button in Mapper tab to populate with 3 demo brands:
- **Starlight Pizza Co.** - API-sourced data
- **Crimson Slice** - CSV-sourced data
- **Pinnacle Pizza** - JSON-sourced data

~500 synthetic locations across all 50 states, with realistic geographic distribution and demographic diversity. Sample data is completely fictional and used only for testing platform functionality.

### Fast Sample Loading
Optimized to run in ~5 seconds (was ~20s before):
- Single shared BigQuery client across all 15 per-brand saves
- Unified cache invalidation (1 call instead of 15)
- Skips table schema probes for empty business/source_types lists

## Configuration & Deployment

### Local Development with `.env`

```bash
cp .env.example .env
# Edit with your values:
WORKFLOW_LOGIN_USER=your_user
WORKFLOW_LOGIN_PASSWORD=your_password
BIGQUERY_PROJECT_ID=your-gcp-project
BIGQUERY_BRONZE_DATASET_ID=birdeye_bronze_listings
BIGQUERY_SILVER_DATASET_ID=birdeye_silver_listings
BIGQUERY_GOLD_DATASET_ID=birdeye_gold_listings
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Claude Code on the Web (Remote Environments)
Automatic environment setup via SessionStart hook (`.claude/hooks/session-start.sh`):
- Installs Python dependencies from `requirements.txt`
- Sets `PYTHONPATH` for module imports
- Validates dependencies are available
- Runs test suite to ensure pytest works

This prevents recurring environment issues and server startup failures.

### Render Deployment

Create a Web Service from GitHub:

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
python -m whitespace_tool workflow-ui --host 0.0.0.0
```

**Environment Variables:**
Add these in Render dashboard:
- All `BIGQUERY_*` and `WORKFLOW_*` variables from `.env`
- Paste full service account JSON into `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- `PORT` is automatically set by Render

Repository includes `render.yaml` for pre-filled config.

### Local Service Account Testing

```bash
cp config/connections/storage.example.json config/connections/storage.json
# Edit credentials_json path or set GOOGLE_APPLICATION_CREDENTIALS
python scripts/test_storage_connection.py
```

Credentials and config are `.gitignore`'d; never commit secrets.

## Logging

Request logs, errors, and BigQuery failures are recorded in `logs/mapper.log` (rotated daily):
- File upload and parsing errors
- Validation failures
- BigQuery operation timeouts
- Save/enrichment errors include a request ID for correlation

Change log directory with `MAPPER_LOG_DIR` environment variable.

## Application State & Sessions

- **Idle timeout:** Sessions expire after 30 minutes of inactivity
- **Login:** Required per session (credentials in `.env`)
- **Caching:** Reporting results cached in SQLite; refreshes hourly or on-demand
- **Soft deletes:** Error records marked `is_deleted` with timestamp; never hard-deleted for audit trail
- **Workflow persistence:** All mappings, templates, and decisions stored in BigQuery

## Performance Characteristics

| Operation | Latency |
|-----------|---------|
| /api/ping | <1ms |
| Mapper page load | ~200ms |
| Parse CSV (1000 rows) | ~800ms |
| Save validated rows | 2-5s (depends on BigQuery) |
| Refresh Reports (BigQuery) | 10-15s (first run) |
| Refresh Reports (SQLite cache) | <1ms (cached) |
| Hourly medallion rebuild (100K rows) | 20-30s |

## Testing

Unit test suite covers:
- Data validation logic (field types, required fields, ZIP validity)
- Enrichment pipeline (coordinate assignment, deduplication)
- Silver layer build
- Gold layer views
- SQLite mirror sync
- Reporting queries
- Sample data loading

Run tests:
```bash
pytest unit_tests/ -q
```

All 135 tests should pass. Tests use mocked BigQuery clients; no live access required.

## Architecture Decisions

### Why Medallion?
- **Bronze:** Immutable audit trail of raw ingested data
- **Silver:** Single source of truth for validated, enriched records (used for individual row lookups, map pins)
- **Gold:** Pre-computed aggregations for reporting (used for metrics, top lists, charts)
- **Separation of concerns:** Each layer has a distinct purpose and refresh cadence

### Why SQLite Cache?
- Reporting queries are almost all aggregation-only (can be pre-computed)
- Pre-aggregations never need to change between hourly refreshes
- Local SQLite is sub-millisecond; eliminates network latency
- BigQuery fallback ensures correctness if cache is missing

### Why Separate Bronze Tables?
- Preserves raw payloads (`raw_record`) for recovery/reprocessing
- Maintains audit trail of all decisions (soft-deletes, error flags)
- Allows incremental analysis and quality reporting
- Source-agnostic schema supports any input format

## Known Limitations & Future Work

- No address-level geocoding (coordinates only; ZIP/city centroids used as fallback)
- No fuzzy duplicate resolution across conflicting source IDs
- No incremental diff reports (full rebuild each refresh)
- No review/feedback ingestion loop (schema reserved for future)

Schema reserves tables `reviews`, `analysis_runs`, and `whitespace_candidates` for future phases.

## Files & Organization

```
.
├── ui/                           # Web UI (HTML/CSS/JavaScript)
│   ├── index.html               # Mapper tab + main layout
│   ├── login.html               # Login page
│   ├── integrations.html        # Reporting tab
│   └── js/mapper.js             # Tab logic and API calls
├── whitespace_tool/             # Python backend
│   ├── workflow_server.py       # HTTP handlers, medallion building
│   ├── warehouse_bigquery.py    # BigQuery client and operations
│   ├── sqlite_cache.py          # SQLite mirror cache
│   ├── data_validation/         # Row validation rules
│   ├── source_adapters/         # CSV/JSON/XML/API parsers
│   └── ...
├── unit_tests/                  # Test suite (135 tests)
├── config/
│   ├── connections/storage.json # BigQuery credentials (local, .gitignore'd)
│   └── workflow_templates/      # Saved mapping templates
├── .cache/
│   └── whitespace_cache.db      # SQLite reporting cache
├── logs/                        # Daily rotating mapper logs
├── .env                         # Environment variables (local, .gitignore'd)
├── .env.example                 # Template
├── requirements.txt             # Python dependencies
└── .claude/
    ├── hooks/session-start.sh   # Cloud IDE environment setup
    └── settings.json            # Hook configuration
```

## Troubleshooting

**Server won't start with "ModuleNotFoundError"**
- Check `PYTHONPATH=.` is set
- Run SessionStart hook: `.claude/hooks/session-start.sh`

**BigQuery dataset not found**
- Verify `BIGQUERY_PROJECT_ID` and dataset names are correct
- Check credentials have BigQuery dataset permissions
- Datasets are auto-created on first API call; check GCP quota

**Reporting queries slow (>10s)**
- SQLite cache may be stale; click "Refresh Reports"
- Hourly scheduler runs at HH:00; check `logs/mapper.log` for refresh status
- Large datasets (>1M rows) may need indexed BigQuery queries; see schema

**Logo/login fails in cloud IDE**
- Run SessionStart hook to set up environment
- Check network proxy allows CDN access to `cdn2.birdeye.com`

## Contributing

1. Create a feature branch from `develop`
2. Make changes and test locally (`pytest unit_tests/`)
3. Commit with clear messages including Co-Author footer
4. Push to feature branch and open a pull request
5. Ensure all 135 tests pass in CI before merge

## License

Assessment prototype. See LICENSE file for terms.
