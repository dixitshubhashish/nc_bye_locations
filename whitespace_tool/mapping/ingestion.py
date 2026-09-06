"""Data ingestion and field mapping execution.

Validates mappings, processes raw source records, executes normalization/validation,
and ingests valid listings and error listings into BigQuery bronze tables.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from whitespace_tool.data_validation import validate_normalized_location, validate_source_row
from whitespace_tool.common.field_registry import load_field_registry
from whitespace_tool.analytics.learning import suggest_from_templates
from whitespace_tool.common.models import utc_now_iso
from whitespace_tool.common.normalization import normalize_location
from whitespace_tool.persistence.sqlite_cache import invalidate_cache
from whitespace_tool.persistence.warehouse_bigquery import push_to_bigquery


def _ws():
    """Lazy import wrapper returning workflow_server module object."""
    import whitespace_tool.workflow_server as ws
    return ws


REQUIRED_MAPPER_FIELDS = {"name", "address", "city", "state", "postal_code"}
REQUIRED_LOCATION_VALUES = ("name", "address", "city", "state", "postal_code")


def validate_mapper(mapper: dict[str, Any], source_fields: list[str], rows: list[dict[str, Any]]) -> list[str]:
    """Validate mapper configuration parameters and required field coverage."""
    errors = []
    if not str(mapper.get("brand", "")).strip():
        errors.append("brand")
    if not str(mapper.get("source_name", "")).strip():
        errors.append("source_name")
    fields = mapper.get("fields")
    if not isinstance(fields, dict):
        return errors + ["fields"]
    missing = sorted(REQUIRED_MAPPER_FIELDS - fields.keys())
    if missing:
        errors.extend(f"fields.{field}" for field in missing)
    unknown = [field for field in fields.values() if field and field not in source_fields]
    if unknown:
        errors.append(f"unknown source fields: {', '.join(sorted(set(unknown)))}")
    if not rows:
        errors.append("source rows")
    return errors


def _scrub_mapper(mapper: dict[str, Any]) -> dict[str, Any]:
    """Remove password and token credential attributes from mapper configuration dictionary."""
    secret_keys = {"token", "password", "key_value", "credentials_json"}

    def scrub(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {child_key: scrub(child, child_key) for child_key, child in value.items() if child_key not in secret_keys}
        if isinstance(value, list):
            return [scrub(child) for child in value]
        return value

    return scrub(mapper)


def _dedupe_listings_against_bronze(
    client: Any, project_id: str, dataset_id: str, new_listings: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Filter out new listing rows whose content_hash already exists in the bronze listings table."""
    if not new_listings:
        return [], 0
    hashes_to_check = {row["content_hash"] for row in new_listings if row.get("content_hash")}
    if not hashes_to_check:
        return new_listings, 0
    try:
        from google.cloud import bigquery
        table_ref = f"{project_id}.{dataset_id}.listings"
        query = f"SELECT DISTINCT content_hash FROM `{table_ref}` WHERE is_deleted IS NOT TRUE AND content_hash IN UNNEST(@hashes)"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("hashes", "STRING", list(hashes_to_check))]
        )
        existing_hashes = {row["content_hash"] for row in client.query(query, job_config=job_config).result()}
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return new_listings, 0
        _ws().LOGGER.warning("bronze_dedupe_query_failed error=%s", exc)
        return new_listings, 0

    if not existing_hashes:
        return new_listings, 0

    matched_updates = [
        (row["content_hash"], row.get("last_observed_at"))
        for row in new_listings
        if row.get("content_hash") in existing_hashes and row.get("last_observed_at")
    ]
    if matched_updates:
        update_query = (
            f"UPDATE `{table_ref}` SET last_observed_at = @last_observed_at, updated_at = CURRENT_TIMESTAMP() "
            f"WHERE content_hash = @content_hash AND is_deleted IS NOT TRUE"
        )
        for chash, obs_at in matched_updates:
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("last_observed_at", "TIMESTAMP", obs_at),
                    bigquery.ScalarQueryParameter("content_hash", "STRING", chash),
                ]
            )
            client.query(update_query, job_config=job_config)

    deduped = [row for row in new_listings if row.get("content_hash") not in existing_hashes]
    skipped = len(new_listings) - len(deduped)
    return deduped, skipped


def _row_error_listing(
    event_id: str,
    business_id: str | None,
    source_type_id: str,
    source_index: int,
    row: dict[str, Any],
    row_errors: list[dict[str, Any]],
    observed_at: Any = None,
) -> dict[str, Any]:
    """Construct error_listings record dictionary for rejected raw row."""
    now = utc_now_iso()
    raw_observed = getattr(observed_at, "isoformat", lambda: str(observed_at or ""))() if observed_at else None
    return {
        "error_listing_id": f"err_{uuid4().hex}",
        "event_id": event_id,
        "business_id": business_id,
        "source_type_id": source_type_id,
        "row_number": source_index + 1,
        "source_row_index": source_index,
        "raw_payload": json.dumps(row, default=str),
        "validation_errors": json.dumps(row_errors),
        "status": "REJECTED",
        "observed_at": raw_observed or now,
        "created_at": now,
        "updated_at": now,
        "is_deleted": False,
        "deleted_on": None,
    }


def save_mapper(
    payload: dict[str, Any],
    client: Any = None,
    skip_cache_invalidation: bool = False,
    assume_tables_exist: bool = False,
    reject_all_invalid: bool = False,
) -> dict[str, Any]:
    """Execute mapping normalization and ingest records into BigQuery bronze tables."""
    mapper = payload["mapper"]
    rows = payload["rows"]
    source_fields = payload.get("source_fields") or _ws().collect_fields(rows)
    save_template = bool(payload.get("save_template", True))
    event_id = payload.get("batch_event_id") or payload.get("event_id") or uuid4().hex
    mapping_id = payload.get("mapping_id")
    row_offset = payload.get("row_offset", 0)
    sample_meta = payload.get("sample_meta") or {}

    errors = validate_mapper(mapper, source_fields, rows)
    if errors:
        raise ValueError(f"Invalid mapper configuration: {', '.join(errors)}")

    source_name = mapper["source_name"]
    source_type = mapper.get("source_type", "csv")
    source_type_id = _ws().ensure_source_type(source_type)
    business_id = _ws().stable_business_id(mapper["brand"])
    template_id = sample_meta.get("template_id") or _ws().stable_template_id(mapper["brand"])
    ingestion_id = sample_meta.get("ingestion_id") or f"ingest_{uuid4().hex}"

    try:
        field_catalog_list = _ws().field_catalog()
    except Exception as exc:
        _ws().LOGGER.exception("field_catalog_fallback error=%s", exc)
        field_catalog_list = load_field_registry()
    custom_slugs = {row["key"] for row in field_catalog_list if row.get("is_custom")}
    business_custom_slugs = {
        row["key"] for row in field_catalog_list if row.get("is_custom") and row.get("business_id") in {None, business_id}
    }
    unauthorized_custom = [
        field for field in mapper.get("fields", {}).keys() if field in custom_slugs and field not in business_custom_slugs
    ]
    if unauthorized_custom:
        raise ValueError(
            f"The custom fields {', '.join(sorted(unauthorized_custom))} belong to another business and cannot be used here."
        )

    field_definitions = _ws().mapper_targets()
    locations = []
    error_listings = []

    for index, row in enumerate(rows):
        source_index = row_offset + index
        row_errors = validate_source_row(row, mapper)
        location = None
        observed_at = None
        try:
            location = normalize_location(row, mapper, source_name, source_index)
            if location is not None:
                observed_at = location.observed_at
            if location is None:
                row_errors.append({
                    "field": "required_location",
                    "reason": "missing brand or ZIP Code",
                    "hint": "Map a business name or provide a fixed business selection, and include a valid ZIP code.",
                    "value": "",
                })
            elif any(not str(getattr(location, field) or "").strip() for field in REQUIRED_LOCATION_VALUES):
                row_errors.append({
                    "field": "required_location",
                    "reason": "missing mandatory value",
                    "hint": "Required location fields must be present before the row can be saved.",
                    "value": "",
                })
            if location is not None:
                row_errors.extend(validate_normalized_location(location, field_definitions))
        except Exception as exc:
            _ws().LOGGER.exception("row_validation_failed event_id=%s row_number=%d", event_id, source_index + 1)
            row_errors.append({
                "field": "row",
                "reason": "row could not be processed",
                "hint": "This row has an unexpected shape or value and was moved to review.",
                "value": str(exc),
            })
        if row_errors:
            error_listings.append(
                _row_error_listing(event_id, business_id, source_type_id, source_index, row, row_errors, observed_at)
            )
        elif location is not None:
            locations.append(location)

    reject_all_invalid = reject_all_invalid or bool(payload.get("reject_all_invalid"))
    if reject_all_invalid and len(rows) > 1 and len(locations) == 0 and len(error_listings) > 0:
        raise ValueError("field mapping looks wrong: all rows failed validation")

    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = client or _ws()._bigquery_client(project_id, credentials_json)

    mapper_id = f"mapper_{uuid4().hex}"
    mapping_id = mapping_id or mapper_id
    config_json = _scrub_mapper(mapper)
    try:
        demographics = _ws()._load_mapped_zip_demographics({location.zip5 for location in locations})
    except Exception as exc:
        _ws().LOGGER.warning("zip_enrichment_lookup_failed_continuing error=%s", exc)
        demographics = {}
    sample_row_meta = {
        "template_id": template_id,
        "ingestion_id": ingestion_id,
        "mapping_id": mapping_id,
        "validation_status": "VALID",
        "is_sample_data": bool(sample_meta.get("is_sample_data")),
        "sample_batch_id": sample_meta.get("sample_batch_id"),
    }
    for location in locations:
        if isinstance(location.raw, dict):
            location.raw.setdefault("__meta", sample_row_meta)
    rows_by_table = _ws().build_table_rows(locations, demographics)
    rows_by_table["listings"], duplicate_listings_skipped = _dedupe_listings_against_bronze(
        client, project_id, dataset_id, rows_by_table["listings"]
    )
    rows_by_table["businesses"] = []
    for record in error_listings:
        record["source_type_id"] = source_type_id
    rows_by_table["source_types"] = []
    rows_by_table["workflow_templates"] = (
        [
            {
                "workflow_template_id": template_id,
                "business_id": business_id,
                "source_type_id": source_type_id,
                "name": source_name,
                "components": json.dumps(
                    {"mapper": config_json, "source_type_id": source_type_id, "sample_meta": sample_meta}, sort_keys=True
                ),
                "archived_components": None,
                "source_configuration": json.dumps(sample_meta.get("source_configuration") or {}, sort_keys=True),
                "is_sample_data": bool(sample_meta.get("is_sample_data")),
                "sample_batch_id": sample_meta.get("sample_batch_id"),
                "is_deleted": False,
                "deleted_on": None,
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            }
        ]
        if save_template
        else []
    )
    rows_by_table["error_listings"] = error_listings
    _ws().push_to_bigquery(
        project_id, dataset_id, rows_by_table, credentials_json, client=client, skip_empty_table_checks=assume_tables_exist
    )
    _ws()._maybe_refresh_after_save(skip_cache_invalidation)
    _ws().LOGGER.info(
        "save_succeeded mapper_id=%s dataset=%s mapped_rows=%d mapped_fields=%d duplicate_listings_skipped=%d",
        mapper_id,
        f"{project_id}.{dataset_id}",
        len(locations),
        len(mapper["fields"]),
        duplicate_listings_skipped,
    )
    return {
        "event_id": event_id,
        "mapper_id": mapper_id,
        "total_rows": len(rows),
        "mapped_rows": len(locations),
        "error_listings": len(error_listings),
        "field_count": len(mapper["fields"]),
        "dataset": f"{project_id}.{dataset_id}",
        "row_offset": row_offset,
        "template_saved": save_template,
        "duplicate_listings_skipped": duplicate_listings_skipped,
    }


def learn_mappings(data: dict[str, Any]) -> dict[str, Any]:
    """Suggest field mapping candidates using historical templates."""
    source_type = str(data.get("source_type", ""))
    source_fields = data.get("source_fields", [])
    if not source_type or not isinstance(source_fields, list):
        raise ValueError("source_type and source_fields are required")
    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.workflow_templates"
    try:
        templates = [
            dict(row)
            for row in client.query(f"SELECT components FROM `{table_ref}` ORDER BY updated_at DESC LIMIT 500").result()
        ]
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"suggestions": {}}
        raise
    return {"suggestions": suggest_from_templates(templates, source_fields, source_type)}
