from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from whitespace_tool.models import LocationRecord, ZipDemographics


LOGGER = logging.getLogger("whitespace_tool.workflow")


TABLE_SCHEMAS: dict[str, list[dict[str, str]]] = {
    "us_zipcodes": [
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
    "businesses": [
        {"name": "business_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "slug", "type": "STRING", "mode": "REQUIRED"},
        {"name": "description", "type": "STRING", "mode": "NULLABLE"},
        {"name": "logo_url", "type": "STRING", "mode": "NULLABLE"},
        {"name": "website_url", "type": "STRING", "mode": "NULLABLE"},
        {"name": "status", "type": "STRING", "mode": "REQUIRED"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "meta_title", "type": "STRING", "mode": "NULLABLE"},
        {"name": "meta_description", "type": "STRING", "mode": "NULLABLE"},
        {"name": "country_of_origin", "type": "STRING", "mode": "NULLABLE"},
    ],
    "listings": [
        {"name": "listing_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "business_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_type_id", "type": "STRING", "mode": "REQUIRED"},
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
    "workflow_templates": [
        {"name": "workflow_template_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "business_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "components", "type": "JSON", "mode": "REQUIRED"},
        {"name": "archived_components", "type": "JSON", "mode": "NULLABLE"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "source_types": [
        {"name": "source_type_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "data_format", "type": "JSON", "mode": "REQUIRED"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "indigestible_records": [
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_type_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "row_number", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "errors", "type": "JSON", "mode": "REQUIRED"},
        {"name": "raw_record", "type": "JSON", "mode": "REQUIRED"},
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
    zip_city_state = {row.zip5: (row.city, row.state) for row in locations}
    return {
        "us_zipcodes": [
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
        "businesses": [],
        "listings": [
            {
                "listing_id": str(uuid4()),
                "business_id": getattr(row, "business_id", row.brand),
                "source_type_id": getattr(row, "source_type_id", ""),
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
        "workflow_templates": [],
        "source_types": [],
        "indigestible_records": [],
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
            bigquery.SchemaField(field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default"))
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
            LOGGER.info("db_batch_load_started table=%s rows=%d", table_ref, len(rows))
            load_job = client.load_table_from_json(rows, table_ref, job_config=bigquery.LoadJobConfig(schema=schema))
            load_job.result()
            if load_job.errors:
                LOGGER.error("db_batch_load_failed table=%s rows=%d error_count=%d errors=%s", table_ref, len(rows), len(load_job.errors), load_job.errors)
                raise RuntimeError(f"Batch load errors for {table_name}: {load_job.errors}")
            LOGGER.info("db_batch_load_succeeded table=%s rows=%d job_id=%s", table_ref, len(rows), load_job.job_id)


def clear_dataset_tables(
    project_id: str,
    dataset_id: str,
    credentials_json: str | None = None,
) -> list[str]:
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("Install the storage client dependencies before clearing saved data.") from exc

    if credentials_json:
        credentials = service_account.Credentials.from_service_account_file(credentials_json)
        client = bigquery.Client(project=project_id, credentials=credentials)
    else:
        client = bigquery.Client(project=project_id)

    dataset_ref = f"{project_id}.{dataset_id}"
    table_refs = [table.reference for table in client.list_tables(dataset_ref)]
    LOGGER.warning("db_clear_started dataset=%s table_count=%d", dataset_ref, len(table_refs))
    deleted: list[str] = []
    for table_ref in table_refs:
        client.delete_table(table_ref, not_found_ok=True)
        deleted.append(table_ref.table_id)
        LOGGER.warning("db_table_deleted dataset=%s table=%s", dataset_ref, table_ref.table_id)
    LOGGER.warning("db_clear_succeeded dataset=%s deleted_count=%d", dataset_ref, len(deleted))
    return deleted