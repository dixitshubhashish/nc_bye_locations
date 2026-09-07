# Implementation Plan: Ingest Sample Locations into Bronze Layer with Resilient Fuzzy Enrichment in Silver Layer

## Overview
Connect the **"Load Sample Dataset"** button directly to the pre-populated `sample_locations` dataset (`source_types`, `businesses`, and `listings`), streaming records into the production Bronze layer (`birdeye_bronze_listings`) alongside real data. All ingested sample records are flagged with `is_sample_data = TRUE`. Following ingestion, the data validation and enrichment pipeline is executed in the backend with error containment, fuzzy alignment (resolving state codes, state names, ZIP codes, and geographic coordinates), and a lightweight/low-priority execution model (`QueryPriority.BATCH` and thread yielding) to ensure it never degrades or stalls active user workflows. Validated and healed records persist into Silver `listings_enriched`, while unresolved records land in `listings_invalid`.

---

## Architecture & Data Flow

```
┌────────────────────────────────────────┐
│  sample_locations (Source Sample DB)   │
│  - source_types                        │
│  - businesses (1,000 brands)           │
│  - listings (22,500 records)           │
└──────────────────┬─────────────────────┘
                   │
                   ▼ [Load Sample Dataset Button /api/sample/load]
┌────────────────────────────────────────────────────────┐
│  birdeye_bronze_listings (Bronze Layer)                │
│  - Real data (is_sample_data IS NOT TRUE)              │
│  - Ingested Sample data (is_sample_data = TRUE)        │
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼ [Background Resilient & Low-Priority Fuzzy Enrichment]
┌────────────────────────────────────────────────────────┐
│  birdeye_silver_listings (Silver Layer)                │
│  - zip_reference (demographics + geo centroids)        │
│  - listings_enriched (valid & fuzzy-healed records)    │
│  - listings_invalid (unresolved / bad data with reason)│
│  - vw_brand_location_top10 & vw_brand_zip_income       │
└────────────────────────────────────────────────────────┘
```

---

## Implemented Components

### 1. Backend Ingestion Workflow (`whitespace_tool/workflow_server.py`)
- **`load_sample_dataset(reset: bool = False)`**:
  - Targets source dataset `sample_locations` (project `keen-device-610`).
  - **Preserves Real Data**: Existing real records (`is_sample_data IS NOT TRUE`) are never touched. Only sample data is cleaned on reset (`DELETE FROM ... WHERE is_sample_data IS TRUE`).
  - **Ingests `source_types`**: Copies source types using `SAFE.PARSE_JSON(s.data_format)` preserving relational integrity.
  - **Ingests `businesses`**: Ingests all 1,000 businesses from `sample_locations.businesses` with `is_sample_data = TRUE` and `sample_batch_id = 'sample_dataset_v1'`.
  - **Ingests `listings`**: Ingests all 22,500 listings from `sample_locations.listings` across all 38 mapped canonical fields (51 total columns) with `is_sample_data = TRUE`.
  - **Non-blocking Dispatch**: Initiates background medallion refresh and returns an immediate response with record counts to the UI.

---

### 2. Validation & Fuzzy Enrichment Engine (`build_silver_layer()`)
- **Fuzzy Alignment Logic in Silver Staging**:
  1. **State Code & State Name Alignment**:
     - Translates full state names ("California" -> "CA", "Texas" -> "TX", etc.) via a standard BigQuery mapping expression.
     - Automatically falls back to verified ZIP reference state codes if `state_code` is missing or mismatched.
  2. **ZIP Code Normalization & Fuzzy Resolution**:
     - Extracts 5-digit postal codes via `REGEXP_EXTRACT(CAST(zip_code AS STRING), r'(\d{5})')`.
     - For missing/alphanumeric/foreign ZIPs:
       - Uses `city_geos` to match city and state to representative city centroids.
  3. **Coordinate Fallback & Healing**:
     - Level 1: `source_listing` (confidence 1.0)
     - Level 2: `zip_centroid` (confidence 0.75)
     - Level 3: `city_state_centroid` (confidence 0.55)
     - Level 4: `unresolved` (routed to `listings_invalid` with reason `unresolved_coordinates`).
  4. **Strict Partitioning into Silver Tables**:
     - `listings_enriched`: Valid records + fuzzy-healed records.
     - `listings_invalid`: Records failing mandatory criteria with explicit `rejection_reason` (e.g. `missing_brand`, `missing_address`, `unresolved_coordinates`).
  5. **Backend Error Containment**:
     - Wrapped in exception guards so errors never surface to the app level as 400/500 failures.

---

### 3. Lightweight & Low-Priority Execution Model
- **BigQuery Batch Priority**:
  - DDL/DML queries execute with `bigquery.QueryJobConfig(priority=bigquery.QueryPriority.BATCH)` when `low_priority=True`.
  - Batch queries do not consume interactive query concurrency slots and queue behind interactive workloads in GCP BigQuery.
- **Thread Yielding & Resource Throttling**:
  - Inter-query pauses (`sleep(0.05)`) between query stages in [`build_silver_layer(low_priority=True)`](file:///Users/shubhashish/nc_bye_locations/whitespace_tool/workflow_server.py) allow the background thread to regularly release CPU and GIL to active HTTP requests.
- **Default Low-Priority Triggers**:
  - Background refresh triggered by "Load Sample Dataset" and hourly scheduled ticks run with `low_priority=True`.
  - The `/api/silver/enrich` endpoint accepts an optional `{"low_priority": true}` parameter.

---

## Verification & Validation Results

### BigQuery Live Dataset Status
- **Bronze Layer (`birdeye_bronze_listings`)**:
  - Real Data (`is_sample_data IS NOT TRUE`): **13,925** listings across 5 businesses (unaltered).
  - Ingested Sample Data (`is_sample_data = TRUE`): **22,500** listings across 1,000 businesses.
- **Silver Layer (`birdeye_silver_listings`)**:
  - `listings_enriched`: **22,099** records validated and fuzzy-healed across 54 states/territories.
  - `listings_invalid`: **9** records routed with explicit rejection reasons.

### Automated Unit Tests
- Full test suite: **137 unit tests ran in 66.5s, 0 failures, 0 errors**.
- Dedicated tests in `unit_tests/test_silver_enrichment.py` verify BigQuery batch priority and background low-priority dispatch.
