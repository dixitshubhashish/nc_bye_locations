# Competitive Whitespace Prototype

Python-only prototype for Birdeye's competitive whitespace assessment. It separates source-specific acquisition from a unified restaurant/location model, stages/pushes unified BigQuery tables, and produces ZIP-level whitespace candidates.

Known assumptions and gaps are tracked in `ASSUMPTIONS_AND_GAPS.md`.

## Run

```bash
.venv/bin/python -m whitespace_tool analyze --config configs/demo.json --output-dir outputs/demo
.venv/bin/python -m whitespace_tool quality-check --config configs/demo.json --output-dir outputs/demo
.venv/bin/python -m whitespace_tool push-bigquery --config configs/demo.json --stage-dir outputs/bigquery --dry-run
```

Fetch the first-module ZIP base table from BigQuery public data:

```bash
.venv/bin/python -m whitespace_tool fetch-public-zips --config configuration/public_us_zips_bigquery.json --output data/us_zips_bigquery.csv
```

Current tested fetch result: 33,791 ZIP geography rows. Known missing ACS fields from the public join are surfaced by quality checks: 868 rows missing population, 1,348 missing median age, and 2,948 missing median household income. The generated full CSV is optional export/debug output; analysis reads ZIP demographics from BigQuery.

Launch the local mapper UI for adding a new brand source:

```bash
python3 -m whitespace_tool mapper-ui
```

Open `http://127.0.0.1:8765/mapper.html`, upload a source, map source columns/paths to BigQuery target fields, then download the generated mapper JSON into `configs/mappers/`.

Supported mapper inputs:

- CSV
- Excel `.xlsx`
- Excel `.xls`
- JSON
- XML
- GET API with JSON response

Each input type is handled by a separate Python backend module under `whitespace_tool/source_preview/`. Excel files expose sheet names in the UI so the user can choose which sheet to map.

The demo config uses small sample files for brand locations only. ZIP geography and demographics are read from BigQuery public datasets.

For a current/realtime-oriented run, start from `configs/live_bigquery.json`. It keeps ZIP demographics in BigQuery, requires live location sources where available, and marks snapshot sources so quality checks surface staleness instead of silently treating old extracts as current.

```bash
python3 -m whitespace_tool quality-check --config configs/live_bigquery.json --output-dir outputs/live
python3 -m whitespace_tool analyze --config configs/live_bigquery.json --output-dir outputs/live
```

To push directly to BigQuery, install `google-cloud-bigquery`, authenticate with Google Application Default Credentials, then run the same `push-bigquery` command without `--dry-run`.

To test the Birdeye BigQuery connection with a service account JSON:

```bash
cp configuration/bigquery_connection.example.json configuration/bigquery_connection.json
python3 -m pip install google-cloud-bigquery google-auth
python3 scripts/test_bigquery_connection.py
```

Put the downloaded service account file at `configuration/keen-device-610-2af9b27dfda3.json`, or edit `credentials_json` in `configuration/bigquery_connection.json`. That local config and credential file are ignored by git.

`configs/live_bigquery.json` uses a `demographics_source` of type `bigquery` and the same warehouse target: `keen-device-610.birdeye_interview`. If you are not using Application Default Credentials, set `credentials_json` in the config or pass `--credentials-json` when pushing warehouse tables.

## Approach

1. Fetch ZIP/ZCTA geography and demographics from BigQuery public data into the unified `us_zips` shape. The current join uses `bigquery-public-data.geo_us_boundaries.zip_codes` for city/county/state/lat/lon and `bigquery-public-data.census_bureau_acs.zip_codes_2018_5yr` for population, income, age, poverty, labor, and housing fields.
2. Keep one source file per brand shape, with source freshness declared in config:
   - `whitespace_tool/sources/dominos_api.py` for a Domino's API JSON response.
   - `whitespace_tool/sources/pizza_hut_kaggle.py` for a Kaggle-style Pizza Hut CSV.
   - `whitespace_tool/sources/little_caesars_json.py` for Little Caesars JSON objects.
3. Use mapper JSON files in `configs/mappers/` to translate each source into the internal schema. Adding a field or changing a source column should be a mapper edit, not analysis rewrites.
4. Run all data quality checks through `whitespace_tool/data_quality.py`: brand coverage, duplicate source keys, required fields, ZIP validity, ZIP-to-demographic joins, missing demographic metrics, coordinate sanity, source tier, sample-file usage, and stale `observed_at` timestamps.
5. Push unified tables to BigQuery using `whitespace_tool/warehouse_bigquery.py`. BigQuery DDL is in `bigquery_schema.sql`; load-ready JSONL and schema files are written to `outputs/bigquery/` during dry runs.
6. Run whitespace analysis from config. The current demo defines similar population profile as z-score distance over `population` and `median_age`; this lives in `configs/demo.json`.

## Outputs

`outputs/demo/brand_locations.csv` contains Domino's, Pizza Hut, and Little Caesars records with ZIP demographics attached.

`outputs/demo/whitespace_zips.csv` contains ZIPs similar to Domino's ZIPs where Domino's is absent. It separates `competitor_present` from `no_tracked_brand_present` and includes median household income plus median age as the extra data point. Median age helps distinguish family/college/retiree trade areas that may have similar population totals but different demand patterns.

`outputs/demo/run_manifest.json` records config, sources, limitations, and summary counts.

`outputs/demo/data_quality_report.json` records the pass/fail result, source counts, brand counts, and issue details.

`outputs/bigquery/` contains one JSONL file per unified BigQuery table plus matching schema JSON files.

## Data Quality Notes

The sample data is not authoritative; it exists to demonstrate architecture. For submission quality, I would pull Domino's from the store API, Pizza Hut from the freshest available public extract or locator-derived source, and Little Caesars from current JSON source objects, then compare counts by state/ZIP against each brand's public locator or another reference. Raw payloads are preserved in `source_observations` so every normalized restaurant can be traced back to its source and observed timestamp.

Known gaps: no address geocoding, no fuzzy duplicate resolution across conflicting source IDs, no incremental diff report yet, and no real review ingestion. The schema reserves `reviews`, `analysis_runs`, and `whitespace_candidates` for those next steps.
