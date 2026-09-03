from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from whitespace_tool.models import LocationRecord, ZipDemographics


LOGGER = logging.getLogger("whitespace_tool.mapper")


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
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "address", "type": "STRING", "mode": "REQUIRED"},
        {"name": "city_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "town", "type": "STRING", "mode": "NULLABLE"},
        {"name": "state_code", "type": "STRING", "mode": "REQUIRED"},
        {"name": "province", "type": "STRING", "mode": "NULLABLE"},
        {"name": "zip_code", "type": "STRING", "mode": "REQUIRED"},
        {"name": "country", "type": "STRING", "mode": "NULLABLE"},
        {"name": "latitude", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "longitude", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "first_observed_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "last_observed_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        # Enhanced location fields
        {"name": "franchise_name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "concept_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "cuisine_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "neighborhood", "type": "STRING", "mode": "NULLABLE"},
        {"name": "district", "type": "STRING", "mode": "NULLABLE"},
        {"name": "phone_number", "type": "STRING", "mode": "NULLABLE"},
        {"name": "website_url", "type": "STRING", "mode": "NULLABLE"},
        {"name": "google_maps_link", "type": "STRING", "mode": "NULLABLE"},
        {"name": "social_media_handles", "type": "STRING", "mode": "NULLABLE"},
        {"name": "operating_hours", "type": "STRING", "mode": "NULLABLE"},
        {"name": "seating_capacity", "type": "INTEGER", "mode": "NULLABLE"},
        {"name": "service_types", "type": "STRING", "mode": "NULLABLE"},
        {"name": "opening_date", "type": "DATE", "mode": "NULLABLE"},
        {"name": "status", "type": "STRING", "mode": "NULLABLE"},
        {"name": "annual_revenue", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "average_ticket_size", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "daily_footfall", "type": "INTEGER", "mode": "NULLABLE"},
        {"name": "monthly_footfall", "type": "INTEGER", "mode": "NULLABLE"},
        {"name": "rental_cost", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "lease_cost", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "population_density", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "average_household_income", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "competitor_count", "type": "INTEGER", "mode": "NULLABLE"},
        {"name": "foot_traffic_score", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "parking_availability", "type": "STRING", "mode": "NULLABLE"},
    ],
    "source_observations": [
        {"name": "brand_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "location_key", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_location_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "observed_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "raw_payload", "type": "JSON", "mode": "NULLABLE"},
    ],
    "reviews": [
        {"name": "brand_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "location_key", "type": "STRING", "mode": "REQUIRED"},
        {"name": "review_source", "type": "STRING", "mode": "REQUIRED"},
        {"name": "rating", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "review_count", "type": "INTEGER", "mode": "NULLABLE"},
        {"name": "observed_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "analysis_runs": [
        {"name": "analysis_run_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "run_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "subject_brand_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "config_json", "type": "JSON", "mode": "REQUIRED"},
        {"name": "generated_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "mapper_configs": [
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "mapper_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "brand_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_type", "type": "STRING", "mode": "REQUIRED"},
        {"name": "field_count", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "config_json", "type": "JSON", "mode": "REQUIRED"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "indigestible_records": [
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "row_number", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "errors", "type": "JSON", "mode": "REQUIRED"},
        {"name": "raw_record", "type": "JSON", "mode": "REQUIRED"},
    ],
    "whitespace_candidates": [
        {"name": "analysis_run_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "zip_code", "type": "STRING", "mode": "REQUIRED"},
        {"name": "whitespace_type", "type": "STRING", "mode": "REQUIRED"},
        {"name": "similarity_distance", "type": "FLOAT", "mode": "REQUIRED"},
        {"name": "competitors_present", "type": "STRING", "mode": "NULLABLE"},
    ],
}


def _scrub_config(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub_config(child)
            for key, child in value.items()
            if key not in {"credentials_json", "headers"} and not key.startswith("_")
        }
    if isinstance(value, list):
        return [_scrub_config(child) for child in value]
    return value


def build_table_rows(
    locations: list[LocationRecord],
    demographics: dict[str, ZipDemographics],
    config: dict[str, Any] | None = None,
    whitespace_rows: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    states = sorted({row.state for row in locations if row.state})
    cities = sorted({(row.city, row.state) for row in locations if row.city and row.state})
    brands = sorted({row.brand for row in locations})
    zip_city_state = {}
    for row in locations:
        zip_city_state.setdefault(row.zip5, (row.city, row.state))

    generated_at = None
    analysis_run_id = None
    analysis_runs: list[dict[str, Any]] = []
    whitespace_candidates: list[dict[str, Any]] = []
    if config is not None and whitespace_rows is not None:
        from whitespace_tool.models import utc_now_iso

        generated_at = utc_now_iso()
        analysis_run_id = f"run_{uuid4().hex}"
        config_for_storage = _scrub_config(config)
        analysis_runs.append(
            {
                "analysis_run_id": analysis_run_id,
                "run_name": config.get("run_name", "competitive_whitespace"),
                "subject_brand_name": config["subject_brand"],
                "config_json": json.dumps(config_for_storage, sort_keys=True),
                "generated_at": generated_at,
            }
        )
        whitespace_candidates = [
            {
                "analysis_run_id": analysis_run_id,
                "zip_code": row["zip_code"],
                "whitespace_type": row["whitespace_type"],
                "similarity_distance": row["similarity_distance"],
                "competitors_present": row["competitors_present"],
            }
            for row in whitespace_rows
        ]

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
                "town": row.town,
                "state_code": row.state,
                "province": row.province,
                "zip_code": row.zip5,
                "country": row.country,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "first_observed_at": row.observed_at,
                "last_observed_at": row.observed_at,
                # Enhanced location fields
                "franchise_name": row.franchise_name,
                "concept_type": row.concept_type,
                "cuisine_type": row.cuisine_type,
                "neighborhood": row.neighborhood,
                "district": row.district,
                "phone_number": row.phone_number,
                "website_url": row.website_url,
                "google_maps_link": row.google_maps_link,
                "social_media_handles": row.social_media_handles,
                "operating_hours": row.operating_hours,
                "seating_capacity": row.seating_capacity,
                "service_types": row.service_types,
                "opening_date": row.opening_date,
                "status": row.status,
                "annual_revenue": row.annual_revenue,
                "average_ticket_size": row.average_ticket_size,
                "daily_footfall": row.daily_footfall,
                "monthly_footfall": row.monthly_footfall,
                "rental_cost": row.rental_cost,
                "lease_cost": row.lease_cost,
                "population_density": row.population_density,
                "average_household_income": row.average_household_income,
                "competitor_count": row.competitor_count,
                "foot_traffic_score": row.foot_traffic_score,
                "parking_availability": row.parking_availability,
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
                "raw_payload": json.dumps(row.raw, sort_keys=True),
            }
            for row in locations
        ],
        "reviews": [],
        "analysis_runs": analysis_runs,
        "whitespace_candidates": whitespace_candidates,
        "mapper_configs": [],
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
        LOGGER.info("db_table_prepare table=%s rows=%d", table_ref, len(rows))
        table = bigquery.Table(table_ref, schema=schema)
        try:
            existing = client.get_table(table_ref)
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                raise
            client.create_table(table)
        else:
            existing_names = {field.name for field in existing.schema}
            missing_fields = [field for field in schema if field.name not in existing_names]
            if missing_fields:
                existing.schema = list(existing.schema) + missing_fields
                client.update_table(existing, ["schema"])
        if rows:
            errors = client.insert_rows_json(table_ref, rows)
            if errors:
                LOGGER.error("db_insert_failed table=%s rows=%d error_count=%d errors=%s", table_ref, len(rows), len(errors), errors)
                raise RuntimeError(f"BigQuery insert errors for {table_name}: {errors}")
            LOGGER.info("db_insert_succeeded table=%s rows=%d", table_ref, len(rows))