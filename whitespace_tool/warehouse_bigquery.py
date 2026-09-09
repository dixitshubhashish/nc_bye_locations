from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from whitespace_tool.models import LocationRecord, ZipDemographics

if TYPE_CHECKING:
    import pandas as pd


def _pandas():
    """Lazily import pandas so this module (and everything that imports it,
    including workflow_server.py at module scope) can still load without
    pandas/pyarrow installed - only the vectorized hashing/load path needs
    them, matching the lazy `from google.cloud import bigquery` pattern used
    throughout the rest of the app for the same reason."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("Install pandas and pyarrow to use vectorized BigQuery row hashing/loading.") from exc
    return pd


# Fields that describe the physical location itself, not the ingestion run
# that produced this row. Deliberately excludes: listing_id (generated
# uuid), location_key (often an index-based fallback id that can differ
# between runs for the same real-world store), source_type_id/template_id/
# ingestion_id/mapping_id/sample_batch_id (ingestion-run metadata, not
# content), first_observed_at/last_observed_at (time-varying by design),
# and is_deleted/deleted_on (mutable state).
CONTENT_HASH_FIELDS: tuple[str, ...] = (
    "business_id", "name", "address", "city_name", "town", "state_code", "province",
    "zip_code", "country", "latitude", "longitude", "franchise_name", "concept_type",
    "cuisine_type", "neighborhood", "district", "phone_number", "website_url",
    "google_maps_link", "social_media_handles", "operating_hours", "seating_capacity",
    "service_types", "opening_date", "status", "annual_revenue", "average_ticket_size",
    "daily_footfall", "monthly_footfall", "rental_cost", "lease_cost",
    "population_density", "average_household_income", "competitor_count",
    "foot_traffic_score", "parking_availability", "ratings", "country_code", "email",
)


def _canonical_hash_payload(row: dict[str, Any], fields: tuple[str, ...] | list[str]) -> str:
    canonical = {key: ("" if row.get(key) is None else str(row.get(key))) for key in fields}
    return json.dumps(canonical, sort_keys=True)


def _is_nullish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (dict, list, tuple, set)):
        return False
    try:
        return bool(_pandas().isna(value))
    except (TypeError, ValueError):
        return False


def _canonical_hash_payload_from_values(values: list[Any], fields: tuple[str, ...] | list[str]) -> str:
    canonical = {field: ("" if _is_nullish(value) else str(value)) for field, value in zip(fields, values)}
    return json.dumps(canonical, sort_keys=True)


def content_hash(row: dict[str, Any]) -> str:
    """Deterministic SHA-256 over a listing's stable content fields."""
    payload = _canonical_hash_payload(row, CONTENT_HASH_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def table_content_hash(table_name: str, row: dict[str, Any]) -> str:
    """Deterministic SHA-256 over all managed columns present in a table row.

    The hash column itself is excluded so the value can be recomputed
    idempotently before each BigQuery load.
    """
    if table_name == "listings":
        return content_hash(row)
    fields = [field["name"] for field in TABLE_SCHEMAS[table_name] if field["name"] != "content_hash"]
    payload = _canonical_hash_payload(row, fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def table_columns(table_name: str) -> list[str]:
    return [field["name"] for field in TABLE_SCHEMAS[table_name]]


def table_hash_columns(table_name: str) -> list[str]:
    if table_name == "listings":
        return list(CONTENT_HASH_FIELDS)
    return [field["name"] for field in TABLE_SCHEMAS[table_name] if field["name"] != "content_hash"]


def table_has_json_fields(table_name: str) -> bool:
    return any(field["type"] == "JSON" for field in TABLE_SCHEMAS[table_name])


def rows_to_dataframe(table_name: str, rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a schema-ordered DataFrame for a managed table."""
    pd = _pandas()
    columns = table_columns(table_name)
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame.from_records(rows).reindex(columns=columns)


def dataframe_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to BigQuery JSON-compatible row dictionaries."""
    pd = _pandas()
    normalized = frame.astype(object).where(pd.notna(frame), None)
    return normalized.to_dict(orient="records")


def add_content_hash_column(table_name: str, frame: pd.DataFrame) -> pd.DataFrame:
    if "content_hash" not in table_columns(table_name):
        return frame
    hashed = frame.copy()
    hash_columns = table_hash_columns(table_name)
    for column in hash_columns:
        if column not in hashed.columns:
            hashed[column] = None
    payloads = hashed[hash_columns].apply(
        lambda row: _canonical_hash_payload_from_values(row.tolist(), hash_columns),
        axis=1,
    )
    hashed["content_hash"] = payloads.map(lambda payload: hashlib.sha256(payload.encode("utf-8")).hexdigest())
    return hashed.reindex(columns=table_columns(table_name))


def rows_to_hashed_dataframe(table_name: str, rows: list[dict[str, Any]]) -> pd.DataFrame:
    return add_content_hash_column(table_name, rows_to_dataframe(table_name, rows))


def hash_rows_by_table(rows_by_table: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {
        table_name: dataframe_to_records(rows_to_hashed_dataframe(table_name, rows))
        for table_name, rows in rows_by_table.items()
    }


LOGGER = logging.getLogger("whitespace_tool.workflow")


TABLE_SCHEMAS: dict[str, list[dict[str, str]]] = {
    "field_catalogs": [
        {"name": "field_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "business_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "slug", "type": "STRING", "mode": "REQUIRED"},
        {"name": "label", "type": "STRING", "mode": "REQUIRED"},
        {"name": "table_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "field_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "data_type", "type": "STRING", "mode": "REQUIRED"},
        {"name": "required", "type": "BOOLEAN", "mode": "REQUIRED"},
        {"name": "hints", "type": "JSON", "mode": "REQUIRED"},
        {"name": "aliases", "type": "JSON", "mode": "REQUIRED"},
        {"name": "is_custom", "type": "BOOLEAN", "mode": "REQUIRED"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        # Removing a custom field archives it rather than deleting the row:
        # listings already written carry that field's values inside
        # listings.custom_fields, and a hard DELETE would strand them with
        # no label, type, or provenance to interpret them by.
        {"name": "is_archived", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "archived_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
    ],
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
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
    ],
    "businesses": [
        {"name": "business_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "slug", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_type_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "description", "type": "STRING", "mode": "NULLABLE"},
        {"name": "logo_url", "type": "STRING", "mode": "NULLABLE"},
        {"name": "website_url", "type": "STRING", "mode": "NULLABLE"},
        {"name": "status", "type": "STRING", "mode": "REQUIRED"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "meta_title", "type": "STRING", "mode": "NULLABLE"},
        {"name": "meta_description", "type": "STRING", "mode": "NULLABLE"},
        {"name": "country_of_origin", "type": "STRING", "mode": "NULLABLE"},
        {"name": "is_reference_data", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "reference_key", "type": "STRING", "mode": "NULLABLE"},
        {"name": "default_source_url", "type": "STRING", "mode": "NULLABLE"},
        {"name": "default_source_name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "is_sample_data", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "sample_batch_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
        {"name": "is_deleted", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "deleted_on", "type": "TIMESTAMP", "mode": "NULLABLE"},
    ],
    "listings": [
        {"name": "listing_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "business_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_type_id", "type": "STRING", "mode": "REQUIRED"},
        # location_key is always populated (normalize_location() generates a
        # fallback when the source doesn't provide one), so it stays
        # REQUIRED. name/address/city_name/state_code/zip_code/country are
        # per-record data fields, not the brand identity - only brand
        # (business_id, tied to the mapper's brand) is mandatory now, so
        # these are NULLABLE like every other non-brand field.
        {"name": "location_key", "type": "STRING", "mode": "REQUIRED"},
        {"name": "name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "address", "type": "STRING", "mode": "NULLABLE"},
        {"name": "city_name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "town", "type": "STRING", "mode": "NULLABLE"},
        {"name": "state_code", "type": "STRING", "mode": "NULLABLE"},
        {"name": "province", "type": "STRING", "mode": "NULLABLE"},
        {"name": "zip_code", "type": "STRING", "mode": "NULLABLE"},
        {"name": "country", "type": "STRING", "mode": "NULLABLE"},
        {"name": "country_code", "type": "STRING", "mode": "NULLABLE"},
        {"name": "latitude", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "longitude", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "first_observed_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "last_observed_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "template_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "ingestion_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "mapping_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "validation_status", "type": "STRING", "mode": "NULLABLE"},
        {"name": "validated", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "enriched_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "max_enriched", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "is_sample_data", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "sample_batch_id", "type": "STRING", "mode": "NULLABLE"},
        # Enhanced location fields
        {"name": "franchise_name", "type": "STRING", "mode": "NULLABLE"},
        {"name": "concept_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "cuisine_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "neighborhood", "type": "STRING", "mode": "NULLABLE"},
        {"name": "district", "type": "STRING", "mode": "NULLABLE"},
        {"name": "phone_number", "type": "STRING", "mode": "NULLABLE"},
        {"name": "email", "type": "STRING", "mode": "NULLABLE"},
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
        {"name": "ratings", "type": "FLOAT", "mode": "NULLABLE"},
        {"name": "custom_fields", "type": "STRING", "mode": "NULLABLE"},
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
        {"name": "is_deleted", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "deleted_on", "type": "TIMESTAMP", "mode": "NULLABLE"},
    ],
    "workflow_templates": [
        {"name": "workflow_template_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "business_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_type_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "components", "type": "JSON", "mode": "REQUIRED"},
        {"name": "archived_components", "type": "JSON", "mode": "NULLABLE"},
        {"name": "source_configuration", "type": "JSON", "mode": "NULLABLE"},
        {"name": "is_sample_data", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "sample_batch_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
        {"name": "is_deleted", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "deleted_on", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "source_types": [
        {"name": "source_type_id", "type": "STRING", "mode": "REQUIRED", "default": "GENERATE_UUID()"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "data_format", "type": "JSON", "mode": "REQUIRED"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
    ],
    "error_listings": [
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "business_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_type_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "row_number", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "errors", "type": "JSON", "mode": "REQUIRED"},
        {"name": "raw_record", "type": "JSON", "mode": "REQUIRED"},
        {"name": "observed_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "template_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "ingestion_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "mapping_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "validation_error_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "country", "type": "STRING", "mode": "NULLABLE"},
        {"name": "is_sample_data", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "sample_batch_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
        {"name": "is_deleted", "type": "BOOLEAN", "mode": "NULLABLE"},
        {"name": "deleted_on", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "is_ai_enriched", "type": "BOOLEAN", "mode": "NULLABLE"},
        # Whether an AI suggestion was available for this row at the moment
        # it entered/re-entered review. Computed once at write time (cheap -
        # the reprocess path already runs the enrichment probe) so the
        # AI-vs-manual pending split can be read straight off the table
        # instead of re-probing the whole queue on every reporting load.
        {"name": "has_ai_suggestion", "type": "BOOLEAN", "mode": "NULLABLE"},
        # How many times a record has come back here after a user submitted
        # a fix that still failed validation - drives the "Review Again"
        # counter in the edit dialog instead of silently re-inserting a
        # fresh row each retry with no memory of prior attempts.
        {"name": "attempt_count", "type": "INTEGER", "mode": "NULLABLE"},
    ],
    "quality_fix_events": [
        {"name": "fix_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "listing_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "row_number", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "fix_type", "type": "STRING", "mode": "REQUIRED"},
        {"name": "processed", "type": "BOOLEAN", "mode": "REQUIRED"},
        {"name": "improved", "type": "BOOLEAN", "mode": "REQUIRED"},
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "reporting_quality_snapshots": [
        {"name": "snapshot_date", "type": "DATE", "mode": "REQUIRED"},
        {"name": "scope_key", "type": "STRING", "mode": "REQUIRED"},
        {"name": "captured_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "total_records", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "invalid_records", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "needs_manual_review", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "ai_fixed", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "manual_fixed", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "zip_missing", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "coordinates_missing", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "duplicate_records", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "zip_completeness_pct", "type": "FLOAT", "mode": "REQUIRED"},
        {"name": "coordinate_completeness_pct", "type": "FLOAT", "mode": "REQUIRED"},
        {"name": "duplicate_rate_pct", "type": "FLOAT", "mode": "REQUIRED"},
        {"name": "stale_records", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "entity_resolution_attempts", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "entity_resolution_success_rate_pct", "type": "FLOAT", "mode": "REQUIRED"},
        {"name": "content_hash", "type": "STRING", "mode": "NULLABLE"},
    ],
}

# Intentionally empty: listings/error_listings were time-partitioned, but
# partitioning adds DML friction (e.g. a partition-filter requirement, or
# UPDATE/DELETE restrictions while data sits in a partition's streaming
# buffer) that isn't worth it for this tool's data volume - error_listings
# soft-delete UPDATEs in particular need to run without those constraints.
# Plain (non-partitioned) tables keep the same schema/clustering either way.
TABLE_PARTITION_SPECS: dict[str, dict[str, Any]] = {}

TABLE_CLUSTER_SPECS: dict[str, list[str]] = {
    "listings": ["state_code", "zip_code", "business_id"],
    "us_zipcodes": ["state_code", "county", "zip_code"],
    "error_listings": ["business_id", "source_type_id"],
    "businesses": ["status", "slug"],
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


def _listing_row(row: LocationRecord) -> dict[str, Any]:
    # Source columns no typed field covers, preserved as a JSON document so
    # a parse whose column list differs from every other parse does not lose
    # data at the bronze write. Deliberately NOT part of CONTENT_HASH_FIELDS:
    # including it would change every previously-stored row's hash and make
    # the next save treat the whole warehouse as new rows.
    extras = getattr(row, "extras", None)
    listing = {
        "custom_fields": json.dumps(extras, sort_keys=True, default=str) if extras else None,
        **(row.raw.get("__meta", {}) if isinstance(row.raw, dict) and isinstance(row.raw.get("__meta"), dict) else {}),
        "listing_id": str(uuid4()),
        "business_id": getattr(row, "business_id", row.brand),
        "is_ai_enriched": bool((row.raw or {}).get("__meta", {}).get("is_ai_enriched", False)) if isinstance(row.raw, dict) else False,
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
        "country_code": getattr(row, "country_code", None),
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
        "email": getattr(row, "email", None),
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
        "ratings": row.ratings,
        "validated": True,
        "enriched_at": None,
        "is_deleted": False,
        "deleted_on": None,
    }
    listing["content_hash"] = content_hash(listing)
    return listing


def build_table_rows(
    locations: list[LocationRecord],
    demographics: dict[str, ZipDemographics],
    config: dict[str, Any] | None = None,
    whitespace_rows: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    zip_city_state = {row.zip5: (row.city, row.state) for row in locations}
    rows_by_table = {
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
        "listings": [_listing_row(row) for row in locations],
        "workflow_templates": [],
        "source_types": [],
        "error_listings": [],
    }
    return hash_rows_by_table(rows_by_table)


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
    write_disposition: str | None = None,
    client: Any = None,
    skip_empty_table_checks: bool = False,
) -> None:
    """skip_empty_table_checks lets a caller that already knows every
    managed table exists (e.g. load_sample_dataset(), which calls the
    _ensure_*_table() helpers before its per-brand loop) skip the
    get_table/create_table round trip entirely for table keys with zero
    rows - those calls have nothing to load and nothing to create, but
    without this flag every call still probes each empty table (businesses,
    source_types, us_zipcodes are always [] from save_mapper()), adding a
    real BigQuery API round trip per table per brand for no reason.
    Defaults to False so every other caller (including ones that rely on an
    empty push to create a table) keeps today's behavior exactly."""
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("Install google-cloud-bigquery and google-auth to push directly to BigQuery.") from exc

    frames_by_table = {
        table_name: rows_to_hashed_dataframe(table_name, rows)
        for table_name, rows in rows_by_table.items()
    }
    if client is None:
        if credentials_json:
            credentials = service_account.Credentials.from_service_account_file(credentials_json)
            client = bigquery.Client(project=project_id, credentials=credentials)
        else:
            client = bigquery.Client(project=project_id)
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    client.create_dataset(dataset_ref, exists_ok=True)

    for table_name, frame in frames_by_table.items():
        rows = dataframe_to_records(frame)
        if not rows and skip_empty_table_checks:
            continue
        schema = [
            bigquery.SchemaField(field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default"))
            for field in TABLE_SCHEMAS[table_name]
        ]
        table_ref = f"{project_id}.{dataset_id}.{table_name}"
        LOGGER.info("db_table_prepare table=%s rows=%d", table_ref, len(rows))
        table = bigquery.Table(table_ref, schema=schema)
        part_spec = TABLE_PARTITION_SPECS.get(table_name)
        if part_spec:
            table.time_partitioning = bigquery.TimePartitioning(
                type_=part_spec["type"],
                field=part_spec["field"]
            )
        cluster_fields = TABLE_CLUSTER_SPECS.get(table_name)
        if cluster_fields:
            table.clustering_fields = cluster_fields
        try:
            existing = client.get_table(table_ref)
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                raise
            client.create_table(table)
        else:
            existing_names = {field.name for field in existing.schema}
            missing_fields = [
                bigquery.SchemaField(field.name, field.field_type, mode="NULLABLE", default_value_expression=field.default_value_expression)
                for field in schema if field.name not in existing_names
            ]
            if missing_fields:
                existing.schema = list(existing.schema) + missing_fields
                client.update_table(existing, ["schema"])
        if rows:
            LOGGER.info("db_batch_load_started table=%s rows=%d", table_ref, len(rows))
            load_config = bigquery.LoadJobConfig(schema=schema)
            if write_disposition:
                load_config.write_disposition = write_disposition
            if hasattr(client, "load_table_from_dataframe") and not table_has_json_fields(table_name):
                try:
                    load_job = client.load_table_from_dataframe(frame, table_ref, job_config=load_config)
                    load_job.result()
                except Exception as exc:
                    LOGGER.warning("dataframe_load_failed_falling_back_to_json table=%s error=%s", table_ref, exc)
                    load_job = client.load_table_from_json(rows, table_ref, job_config=load_config)
                    load_job.result()
            else:
                load_job = client.load_table_from_json(rows, table_ref, job_config=load_config)
                load_job.result()
            if load_job.errors:
                LOGGER.error("db_batch_load_failed table=%s rows=%d error_count=%d errors=%s", table_ref, len(rows), len(load_job.errors), load_job.errors)
                raise RuntimeError(f"Batch load errors for {table_name}: {load_job.errors}")
            LOGGER.info("db_batch_load_succeeded table=%s rows=%d job_id=%s", table_ref, len(rows), load_job.job_id)


PROTECTED_DATASETS: set[str] = {"sample_locations"}


def _assert_not_protected_dataset(dataset_name: str) -> None:
    ds = str(dataset_name).split(".")[-1].strip().lower()
    if ds in PROTECTED_DATASETS:
        raise PermissionError(f"CRITICAL SAFETY RULE: '{ds}' is an immutable reference dataset. No delete, drop, update, or truncate operations are permitted.")


def _clear_dataset_tables_with_client(client: Any, dataset_ref: str) -> dict[str, list[str]]:
    _assert_not_protected_dataset(dataset_ref)
    preserved_tables = {"us_zipcodes", "field_catalogs", "field_catalog", "source_types", "workflow_templates", "quality_fix_events"}
    table_refs = [table.reference for table in client.list_tables(dataset_ref) if table.table_id not in preserved_tables]
    LOGGER.warning("db_clear_started dataset=%s table_count=%d", dataset_ref, len(table_refs))
    soft_deleted: list[str] = []
    truncated: list[str] = []
    soft_delete_tables = {"businesses", "listings", "error_listings"}
    
    # Execute batch soft delete queries in single API calls for optimal speed
    for table_ref in table_refs:
        t_id = table_ref.table_id
        if t_id in soft_delete_tables:
            query = f"""
            ALTER TABLE `{dataset_ref}.{t_id}` ADD COLUMN IF NOT EXISTS is_deleted BOOL;
            ALTER TABLE `{dataset_ref}.{t_id}` ADD COLUMN IF NOT EXISTS deleted_on TIMESTAMP;
            ALTER TABLE `{dataset_ref}.{t_id}` ADD COLUMN IF NOT EXISTS validated BOOL;
            ALTER TABLE `{dataset_ref}.{t_id}` ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMP;
            UPDATE `{dataset_ref}.{t_id}` SET is_deleted = TRUE, deleted_on = CURRENT_TIMESTAMP() WHERE is_deleted IS NOT TRUE;
            """
            client.query(query).result()
            soft_deleted.append(t_id)
            LOGGER.warning("db_table_soft_deleted dataset=%s table=%s", dataset_ref, t_id)
            continue
        client.query(f"TRUNCATE TABLE `{dataset_ref}.{t_id}`").result()
        truncated.append(t_id)
        LOGGER.warning("db_table_truncated dataset=%s table=%s", dataset_ref, t_id)
        
    LOGGER.warning("db_clear_succeeded dataset=%s soft_deleted_count=%d truncated_count=%d", dataset_ref, len(soft_deleted), len(truncated))
    return {"soft_deleted_tables": soft_deleted, "truncated_tables": truncated}


def clear_dataset_tables(
    project_id: str,
    dataset_id: str,
    credentials_json: str | None = None,
) -> dict[str, list[str]]:
    _assert_not_protected_dataset(dataset_id)
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
    return _clear_dataset_tables_with_client(client, dataset_ref)


def drop_dataset_tables(
    project_id: str,
    dataset_id: str,
    credentials_json: str | None = None,
) -> dict[str, list[str]]:
    _assert_not_protected_dataset(dataset_id)
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("Install the storage client dependencies before deleting master data.") from exc

    if credentials_json:
        credentials = service_account.Credentials.from_service_account_file(credentials_json)
        client = bigquery.Client(project=project_id, credentials=credentials)
    else:
        client = bigquery.Client(project=project_id)

    dataset_ref = f"{project_id}.{dataset_id}"
    table_items = list(client.list_tables(dataset_ref))
    LOGGER.warning("db_master_delete_started dataset=%s object_count=%d", dataset_ref, len(table_items))
    dropped: list[str] = []
    dropped_objects: list[dict[str, str]] = []
    for table in table_items:
        client.delete_table(table.reference, not_found_ok=True)
        object_type = str(getattr(table, "table_type", "") or "TABLE")
        dropped.append(table.table_id)
        dropped_objects.append({"name": table.table_id, "type": object_type})
        LOGGER.warning("db_master_object_dropped dataset=%s object=%s type=%s", dataset_ref, table.table_id, object_type)
    LOGGER.warning("db_master_delete_succeeded dataset=%s dropped_count=%d", dataset_ref, len(dropped))
    return {"dropped_tables": dropped, "dropped_objects": dropped_objects}
