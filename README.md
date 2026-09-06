# Competitive Whitespace Prototype

Web-based platform for restaurant/location data ingestion, validation, enrichment, and competitive gap analysis. Multi-source data flows through a medallion architecture (Bronze → Silver → Gold) with real-time reporting and data quality metrics.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env                    # Set: WORKFLOW_LOGIN_USER, WORKFLOW_LOGIN_PASSWORD, BIGQUERY_PROJECT_ID, etc.
python -m whitespace_tool workflow-ui   # Open http://127.0.0.1:8765/
```

**Environment Variables:**
- `WORKFLOW_LOGIN_USER`/`WORKFLOW_LOGIN_PASSWORD` - Web UI auth
- `BIGQUERY_PROJECT_ID`, `BIGQUERY_BRONZE_DATASET_ID`, `BIGQUERY_SILVER_DATASET_ID`, `BIGQUERY_GOLD_DATASET_ID`
- `GOOGLE_APPLICATION_CREDENTIALS` or `GOOGLE_APPLICATION_CREDENTIALS_JSON` - GCP service account

## Application: Four-Tab Workflow

**1. Mapper** — Upload location data (CSV, Excel, JSON, XML, API, Python Editor), auto-map columns to schema, validate, save with templates.

**2. Review Error Listings** — Fix validation failures: add missing required fields (name, address, ZIP), see enrichment status, reprocess.

**3. Template Library** — Manage mapping templates, preview source fields, reuse across brands.

**4. Reporting** — Multi-brand filter, view location counts by state/city/ZIP, data enrichment % (fully/geo/ZIP/city-enriched), coordinate sources, data quality metrics, interactive map (green=full coords, blue=ZIP centroid, red=invalid), gap analysis.

## Technical Architecture: Medallion + Cache

```
Bronze (Raw)
├─ listings, businesses, error_listings, us_zipcodes
└─ Validation via data_validation/, invalid rows → error_listings

       ↓ (hourly + on-demand)

Silver (Enriched)
├─ listings_enriched: validated + deduplicated + coords filled from ZIP/city centroids
├─ Enrichment status: fully_enriched|geo_enriched|zip_enriched|city_enriched|minimal
└─ Coordinate source: source_listing|zip_centroid|city_state_centroid

       ↓ (same refresh)

Gold (Views)
├─ vw_zip_brand_activity, vw_state_summary, vw_city_summary, vw_brand_summary
├─ vw_listing_quality_summary, vw_geo_reference
└─ Pre-aggregated for reporting speed

       ↓ (sync)

SQLite Mirror (.cache/whitespace_cache.db)
└─ Local copy: <1ms latency (vs. 13.5s BigQuery)
```

**Refresh:** Hourly background thread (reconciles with on-demand manual refresh via REPORTING_REFRESH_LOCK). All tables partitioned/clustered by (state_code, zip_code, business_id).

## Data Flow

1. **Upload** (Mapper) → parse & validate → Bronze (listings, error_listings)
2. **Enrich** (hourly/on-demand) → Silver (coords from ZIP/city, dedup, track source)
3. **Aggregate** (hourly/on-demand) → Gold views (pre-computed counts/summaries)
4. **Cache** → SQLite mirror syncs Gold results
5. **Report** → Reporting tab queries Gold views (SQLite first, BigQuery fallback) + Silver for individual records (map pins, samples)

**Error Recovery:** Fix rows in Review tab, reprocess → back to Bronze validation step.

## Sample Data

Click "Load Sample Dataset" in Mapper for 3 demo brands (~500 synthetic locations):
- Starlight Pizza Co. (API source)
- Crimson Slice (CSV source)
- Pinnacle Pizza (JSON source)

All fictional; purely for testing. Fast load (~5s): single BigQuery client + unified cache invalidation.

## Deployment

**Local:** `.env` + `python -m whitespace_tool workflow-ui --host 127.0.0.1 --port 8765`

**Cloud IDE (Claude Code on web):** SessionStart hook (`.claude/hooks/session-start.sh`) auto-installs deps, sets PYTHONPATH, validates pytest.

**Render:** Build: `pip install -r requirements.txt` → Start: `python -m whitespace_tool workflow-ui --host 0.0.0.0`. Add env vars in Render dashboard; paste service account JSON into `GOOGLE_APPLICATION_CREDENTIALS_JSON`.

## Key Features

- **Multi-source ingest** — 7 formats (CSV, Excel, JSON, XML, API, Python, manual)
- **Validation** — Required fields (name, address, ZIP), type checks, ZIP lookup, dedup detection
- **Enrichment** — Auto-fill coords from ZIP/city centroids; track source; % completeness per enrichment level
- **Reporting** — Multi-brand filtering, 50+ metrics, <1ms SQLite cache, interactive map, quality dashboard
- **Audit trail** — Soft-deletes only; raw_record preserved; all logs in `logs/mapper.log`
- **Templates** — Save/reuse mappings; predefined for demo brands
- **Caching** — SQLite mirror for 13.5x faster reporting; auto-invalidate on data change
- **Sessions** — Idle timeout 30min; login required; state in BigQuery

## Testing & Logging

Run: `pytest unit_tests/ -q` (135 tests, <2s, mocked BigQuery). Logs: `logs/mapper.log` (daily rotate). Errors include request ID for correlation.

## Performance

| Operation | Latency |
|-----------|---------|
| API ping | <1ms |
| Parse 1K rows | ~800ms |
| Save validated rows | 2-5s |
| Refresh (BigQuery) | 10-15s |
| Refresh (SQLite) | <1ms |

---

**Architecture:** Medallion (Bronze→Silver→Gold) with SQLite cache + hourly scheduler.  
**Frontend:** HTML/CSS/JS tabs (Mapper, Errors, Templates, Reporting).  
**Backend:** Python HTTP server, BigQuery client, SQLite mirror, validators, enrichment logic.  
All configs in `.env` (local) or Render environment variables. See `docs/assumptions_and_gaps.md` for known gaps.
