# Assumptions And Gaps

This document tracks known assumptions, data gaps, and deliberate tradeoffs in the competitive whitespace prototype. Keep this updated as sources, schema, or analysis logic changes.

## ZIP And Demographic Data

- ZIP geography and demographics currently come only from BigQuery public datasets.
- ZIP geography source: `bigquery-public-data.geo_us_boundaries.zip_codes`.
- Demographic source: `bigquery-public-data.census_bureau_acs.zip_codes_2018_5yr`.
- The ACS table is ZCTA-based. ZCTAs are Census approximations of ZIP areas, not exact USPS delivery ZIP codes.
- Some ZIPs in the geography table do not have matching ACS demographic values.
- Current observed public-data gaps from the joined ZIP table:
  - 868 rows missing population.
  - 1,348 rows missing median age.
  - 2,948 rows missing median household income.
- ZIP-level latitude/longitude uses the BigQuery geography table internal point, not a restaurant-level geocode.
- City/county/state values describe ZIP geography and may not perfectly match postal preferred city names or business addresses.

## Brand Location Data

- Domino's is modeled as a live API-shaped source, but the checked-in demo uses a sample JSON payload.
- Pizza Hut is modeled as a Kaggle/current CSV-shaped source. It should be treated as a snapshot unless refreshed from a current source.
- Little Caesars is modeled as JSON objects. It should be treated as a snapshot unless refreshed from a current source.
- Demo brand data is intentionally small and not authoritative.
- Brand coverage is not assumed complete until source counts are compared against an external reference such as public locators or known store counts.
- `observed_at` is required conceptually so stale source data can be detected, but some public/snapshot inputs may need this value stamped at acquisition time.

## Normalization And Mapping

- The mapper UI helps map CSV/JSON source fields into the internal schema, but it does not prove semantic correctness.
- The mapper UI supports CSV, Excel `.xlsx`, Excel `.xls`, JSON, XML, and GET JSON API previews through separate Python backend modules.
- Excel files expose sheet names in the UI so the user can choose which sheet to map.
- Nested JSON paths are supported with dot notation.
- A missing `location_id` is generated from brand, ZIP, and row number. This is acceptable for demo continuity but weaker for long-term change tracking.
- Source-specific raw payloads are preserved in `source_observations` for traceability.
- Current standard location fields are:
  - brand
  - location_id
  - name
  - address
  - city
  - state
  - postal_code
  - latitude
  - longitude
  - observed_at

## Deduplication

- Deduplication is currently simple: brand, source location ID, address, and ZIP.
- It does not yet perform fuzzy address matching.
- It does not yet resolve conflicts where two sources identify the same physical store with different IDs.
- It does not yet use phone number, website URL, geospatial distance, or normalized address tokens for matching.

## Whitespace Analysis

- Current similarity logic uses z-score distance over configured demographic metrics.
- Demo config currently uses population and median age.
- Median household income is included in whitespace output but is not necessarily part of the similarity definition unless configured.
- ZIPs are treated as candidate markets; the model does not yet account for drive time, store trade areas, delivery radius, road networks, or cannibalization.
- A ZIP is considered occupied by a brand if at least one normalized restaurant record exists in that ZIP.
- Competitor whitespace means Domino's is absent but at least one configured competitor is present.
- Empty whitespace means none of the tracked brands are present in that ZIP.

## BigQuery Warehouse

- BigQuery is the only database/warehouse target.
- Local generated JSONL files are dry-run/staging artifacts, not the source of truth.
- BigQuery table definitions are in `bigquery_schema.sql`.
- BigQuery insert logic currently creates tables if missing and inserts JSON rows.
- There is no production-grade merge/upsert strategy yet.
- There is no partitioning or clustering strategy yet.
- There is no table versioning or backfill strategy yet.

## Data Quality

- Quality checks currently cover:
  - configured brand coverage
  - duplicate location keys
  - required location fields
  - ZIP format validity
  - ZIP-to-demographics match
  - missing demographic metrics
  - broad coordinate sanity
  - demo/sample source usage
  - non-live source usage in live mode
  - stale `observed_at` timestamps
- Quality warnings do not block warehouse dry-run/push unless they are classified as errors.
- Missing demographic fields are warnings today, not hard failures, because public data gaps are expected.

## Deliberately Not Built Yet

- Full live acquisition for all three brands.
- Address geocoding and address standardization.
- Fuzzy duplicate resolution.
- Franchisee/operator enrichment.
- Reviews ingestion.
- Incremental diff reporting between runs.
- BigQuery merge/upsert jobs.
- Market definitions beyond ZIP prefix filtering and all-US.
- Map visualization.
- Automated source coverage benchmarking against locator counts.

## Current Positioning

This is a reusable prototype, not a production data platform. The strongest parts are the source separation, mapper-driven normalization, BigQuery-native ZIP/demographic base, data quality visibility, and configurable analysis logic. The weakest parts are source completeness, dedupe sophistication, and lack of true incremental warehouse loading.
