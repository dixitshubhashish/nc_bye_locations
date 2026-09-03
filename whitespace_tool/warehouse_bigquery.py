from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from whitespace_tool.models import LocationRecord, ZipDemographics


TABLE_SCHEMAS: dict[str, list[dict[str, str]]] = {
    "states": [
        {"name": "state_code", "type": "STRING", "mode": "REQUIRED"},
        {"name": "state_name", "type": "STRING", "mode": "NULLABLE"},
    ],
    "cities": [
        {"name": "city_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "state_code", "type": "STRING", "mode": "REQUIRED"},
    ],
    "us_zips": [
        {"name": "zip_code", "type": "STRING", "mode": "REQUIRED"},
        {"name": "city_name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "county", "type": "STRING", "mode": "NULLABLE"},
        {"name": "state_code", "type": "STRING", "mode": "NULLABLE"},
        {"name": "state_name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "latitude", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "longitude", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "population", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "median_household_income", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "median_age", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "households", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "income_per_capita", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "poverty", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "employed_population", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "unemployed_population", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "housing_units", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "source", "type": "STRING", "mode": "REQUIRED"},
    ],
    "brands": [
        {"name": "brand_name", "type": "STRING", "mode": "REQUIRED"},
    ],
    "restaurants": [
        {"name": "brand_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "location_key", "type": "STRING", "mode": "REQUIRED"},
        {"name": "name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "address", "type": "STRING", "mode": "NULLABLE"},
        {"name": "city_name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "state_code", "type": "STRING", "mode": "NULLABLE"},
        {"name": "zip_code", "type": "STRING", "mode": "REQUIRED"},
        {"name": "latitude", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "longitude", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "first_observed_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "last_observed_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
    ],
    "source_observations": [
        {"name": "brand_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "location_key", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_location_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "observed_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "raw_payload", "type": "JSON", "mode": "NULLABLE"},
    ],
}


def build_table_rows(
    locations: list[LocationRecord],
    demographics: dict[str, ZipDemographics],
) -> dict[str, list[dict[str, Any]]]:
    states = sorted({row.state for row in locations if row.state})
    cities = sorted({(row.city, row.state) for row in locations if row.city and row.state})
    brands = sorted({row.brand for row in locations})
    zip_city_state = {}
    for row in locations:
        zip_city_state.setdefault(row.zip5, (row.city, row.state))

    return {
        "states": [{"state_code": state, "state_name": None} for state in states],
        "cities": [{"city_name": city, "state_code": state} for city, state in cities],
        "brands": [{"brand_name": brand} for brand in brands],
        "us_zips": [
            {
                "zip_code": demo.zip_code,
                "city_name": demo.city or zip_city_state.get(demo.zip_code, (None, None))[0],
                "county": demo.county,
                "state_code": demo.state_code or zip_city_state.get(demo.zip_code, (None, None))[1],
                "state_name": demo.state_name,
                "latitude": demo.latitude,
                "longitude": demo.longitude,
                "population": demo.population,
                "median_household_income": demo.median_household_income,
                "median_age": demo.median_age,
                "households": demo.households,
                "income_per_capita": demo.income_per_capita,
                "poverty": demo.poverty,
                "employed_population": demo.employed_population,
                "unemployed_population": demo.unemployed_population,
                "housing_units": demo.housing_units,
                "source": demo.source,
            }
            for demo in demographics.values()
        ],
        "restaurants": [
            {
                "brand_name": row.brand,
                "location_key": row.location_id,
                "name": row.name,
                "address": row.address,
                "city_name": row.city,
                "state_code": row.state,
                "zip_code": row.zip5,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "first_observed_at": row.observed_at,
                "last_observed_at": row.observed_at,
            }
            for row in locations
        ],
        "source_observations": [
            {
                "brand_name": row.brand,
                "location_key": row.location_id,
                "source_name": row.source,
                "source_location_id": row.location_id,
                "observed_at": row.observed_at,
                "raw_payload": row.raw,
            }
            for row in locations
        ],
    }


def write_bigquery_jsonl(output_dir: str | Path, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for table_name, rows in rows_by_table.items():
        with (out / f"{table_name}.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True))
                fh.write("\n")


def write_bigquery_schema(output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for table_name, schema in TABLE_SCHEMAS.items():
        with (out / f"{table_name}_schema.json").open("w", encoding="utf-8") as fh:
            json.dump(schema, fh, indent=2)
            fh.write("\n")


def push_to_bigquery(
    project_id: str,
    dataset_id: str,
    rows_by_table: dict[str, list[dict[str, Any]]],
    credentials_json: str | None = None,
) -> None:
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("Install google-cloud-bigquery and google-auth to push directly to BigQuery.") from exc

    if credentials_json:
        credentials = service_account.Credentials.from_service_account_file(credentials_json)
        client = bigquery.Client(project=project_id, credentials=credentials)
    else:
        client = bigquery.Client(project=project_id)
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    client.create_dataset(dataset_ref, exists_ok=True)

    for table_name, rows in rows_by_table.items():
        schema = [
            bigquery.SchemaField(field["name"], field["type"], mode=field["mode"])
            for field in TABLE_SCHEMAS[table_name]
        ]
        table_ref = f"{project_id}.{dataset_id}.{table_name}"
        table = bigquery.Table(table_ref, schema=schema)
        client.create_table(table, exists_ok=True)
        if rows:
            errors = client.insert_rows_json(table_ref, rows)
            if errors:
                raise RuntimeError(f"BigQuery insert errors for {table_name}: {errors}")
