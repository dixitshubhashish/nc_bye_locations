"""Field catalog, custom fields, and schema target definitions.

Provides field catalog operations, custom field management, and alias definitions.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from whitespace_tool.common.field_registry import load_field_registry
from whitespace_tool.common.models import utc_now_iso
from whitespace_tool.persistence.sqlite_cache import invalidate_cache
from whitespace_tool.persistence.warehouse_bigquery import TABLE_SCHEMAS


def _ws():
    """Lazy import wrapper returning workflow_server module object."""
    import whitespace_tool.workflow_server as ws
    return ws


def mapper_targets_with_status() -> dict[str, Any]:
    """Retrieve mapping target fields along with catalog storage status."""
    try:
        return {"fields": field_catalog(), "source": "managed"}
    except Exception as exc:
        _ws().LOGGER.exception("field_catalog_fallback error=%s", exc)
        return {
            "fields": load_field_registry(),
            "source": "default",
            "warning": "Default field definitions were loaded.",
        }


def mapper_targets() -> list[dict[str, Any]]:
    """Retrieve list of target schema fields for mapper UI."""
    return mapper_targets_with_status()["fields"]


def field_catalog() -> list[dict[str, Any]]:
    """Fetch and sync field definitions from the BigQuery field_catalogs table."""
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    _ws()._ensure_dataset(client, project_id, dataset_id)
    table_ref = f"{project_id}.{dataset_id}.field_catalogs"
    schema = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")
        )
        for field in TABLE_SCHEMAS["field_catalogs"]
    ]
    created = False
    try:
        existing_table = client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(bigquery.Table(table_ref, schema=schema))
        created = True
    else:
        existing_names = {field.name for field in existing_table.schema}
        if "business_id" not in existing_names:
            client.query(f"ALTER TABLE `{table_ref}` ADD COLUMN business_id STRING").result()
    if created:
        legacy_ref = f"{project_id}.{dataset_id}.field_catalog"
        try:
            client.get_table(legacy_ref)
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                raise
        else:
            client.query(
                f"INSERT INTO `{table_ref}` (field_id, business_id, slug, label, table_name, field_name, data_type, required, hints, aliases, is_custom, created_at, updated_at) SELECT field_id, NULL, slug, label, table_name, field_name, data_type, required, hints, aliases, is_custom, created_at, updated_at FROM `{legacy_ref}`"
            ).result()

    def _registry_seed_row(field: dict[str, Any], now: str) -> dict[str, Any]:
        """Convert standard field definition into BigQuery table seed dictionary."""
        return {
            "field_id": str(uuid4()),
            "business_id": None,
            "slug": field["key"],
            "label": field["label"],
            "table_name": field["table"],
            "field_name": field["field"],
            "data_type": field["type"],
            "required": field.get("required", False),
            "hints": json.dumps(field.get("hints", [])),
            "aliases": json.dumps([]),
            "is_custom": False,
            "created_at": now,
            "updated_at": now,
        }

    rows = [dict(row) for row in client.query(f"SELECT * FROM `{table_ref}` ORDER BY is_custom, label").result()]
    if not rows:
        now = utc_now_iso()
        seed = [_registry_seed_row(field, now) for field in load_field_registry()]
        load_job = client.load_table_from_json(seed, table_ref, job_config=bigquery.LoadJobConfig(schema=schema))
        load_job.result()
        rows = [dict(row) for row in client.query(f"SELECT * FROM `{table_ref}` ORDER BY is_custom, label").result()]
    else:
        existing_standard_slugs = {row["slug"] for row in rows if not row.get("is_custom")}
        missing = [field for field in load_field_registry() if field["key"] not in existing_standard_slugs]
        if missing:
            now = utc_now_iso()
            seed = [_registry_seed_row(field, now) for field in missing]
            load_job = client.load_table_from_json(seed, table_ref, job_config=bigquery.LoadJobConfig(schema=schema))
            load_job.result()
            rows = [dict(row) for row in client.query(f"SELECT * FROM `{table_ref}` ORDER BY is_custom, label").result()]
    for row in rows:
        for key in ("created_at", "updated_at"):
            if hasattr(row.get(key), "isoformat"):
                row[key] = row[key].isoformat()
        for key in ("hints", "aliases"):
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])
        row["key"] = row.pop("slug")
        row["table"] = row.pop("table_name")
        row["field"] = row.pop("field_name")
        row["type"] = row.pop("data_type")
        row["hints"] = list(dict.fromkeys(row.get("hints", []) + row.get("aliases", [])))
    return rows


def add_field_alias(data: dict[str, Any]) -> dict[str, Any]:
    """Add a source column alias to a standard target field."""
    from google.cloud import bigquery

    if str(data.get("password", "")) != "54321":
        raise ValueError("Administrative password required")
    field_key = str(data.get("field_key", "")).strip()
    alias = str(data.get("alias", "")).strip()
    if not field_key or not alias:
        raise ValueError("Standard field and source label are required")
    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.field_catalogs"
    current_query = f"SELECT aliases FROM `{table_ref}` WHERE slug = @slug LIMIT 1"
    current_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("slug", "STRING", field_key)])
    current = list(client.query(current_query, job_config=current_config).result())
    if not current:
        raise ValueError("Standard field was not found")
    current_aliases = current[0]["aliases"]
    if isinstance(current_aliases, str):
        current_aliases = json.loads(current_aliases)
    aliases = json.dumps(sorted(set(current_aliases or []) | {alias}))
    query = f"UPDATE `{table_ref}` SET aliases = @aliases, updated_at = CURRENT_TIMESTAMP() WHERE slug = @slug"
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("slug", "STRING", field_key),
            bigquery.ScalarQueryParameter("aliases", "JSON", aliases),
        ]
    )
    client.query(query, job_config=config).result()
    return {"field_key": field_key, "alias": alias}


def _to_camel_case(text: str) -> str:
    """Convert input string to camelCase formatting."""
    s = re.sub(r"[^a-zA-Z0-9]+", " ", text).title().replace(" ", "")
    return s[0].lower() + s[1:] if s else ""


def create_custom_field(data: dict[str, Any]) -> dict[str, Any]:
    """Create a new custom business-scoped field definition."""
    label = str(data.get("label", "")).strip()
    if not label:
        raise ValueError("Field label is required")
    if str(data.get("password", "")) != "54321":
        raise ValueError("Administrative password required (use '54321')")
    business_id = str(data.get("business_id", "")).strip()
    if not business_id:
        raise ValueError("Select a business before adding a custom field")

    raw_slug = str(data.get("slug", "")).strip() or label
    slug = _to_camel_case(raw_slug)
    if not slug:
        raise ValueError("Field slug must contain alphanumeric characters")

    norm_label = re.sub(r"[^a-z0-9]", "", label.lower())
    norm_slug = re.sub(r"[^a-z0-9]", "", slug.lower())

    for std in load_field_registry():
        std_key_norm = re.sub(r"[^a-z0-9]", "", str(std.get("key", "")).lower())
        std_label_norm = re.sub(r"[^a-z0-9]", "", str(std.get("label", "")).lower())
        std_hints_norm = {re.sub(r"[^a-z0-9]", "", str(h).lower()) for h in std.get("hints", [])}

        if (
            (norm_slug and norm_slug in (std_key_norm, std_label_norm))
            or (norm_label and norm_label in (std_key_norm, std_label_norm))
            or norm_slug in std_hints_norm
            or norm_label in std_hints_norm
        ):
            raise ValueError(
                f"Field '{label}' (slug: '{slug}') matches built-in standard field '{std['label']}'. "
                f"Standard fields are already built into the platform schema and cannot be re-created as custom fields."
            )

    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    catalog = field_catalog()
    for row in catalog:
        if row.get("business_id") in {None, business_id}:
            row_key_norm = re.sub(r"[^a-z0-9]", "", str(row.get("key", "")).lower())
            row_label_norm = re.sub(r"[^a-z0-9]", "", str(row.get("label", "")).lower())
            if (norm_slug and norm_slug in (row_key_norm, row_label_norm)) or (
                norm_label and norm_label in (row_key_norm, row_label_norm)
            ):
                raise ValueError(
                    f"A custom field similar to '{label}' (slug: '{slug}') already exists as '{row.get('label', row.get('key'))}'."
                )
    table_ref = f"{project_id}.{dataset_id}.field_catalogs"
    now = utc_now_iso()
    field = {
        "field_id": str(uuid4()),
        "business_id": business_id,
        "slug": slug,
        "label": label,
        "table_name": "listings",
        "field_name": slug,
        "data_type": data.get("type", "string"),
        "required": False,
        "hints": json.dumps([slug]),
        "aliases": json.dumps([]),
        "is_custom": True,
        "created_at": now,
        "updated_at": now,
    }
    errors = client.insert_rows_json(table_ref, [field])
    if errors:
        raise RuntimeError(f"Custom field could not be saved: {errors}")
    return {
        "field": {
            "key": slug,
            "label": label,
            "table": "listings",
            "field": slug,
            "type": field["data_type"],
            "required": False,
            "hints": [slug],
            "is_custom": True,
        }
    }


def delete_custom_field(data: dict[str, Any]) -> dict[str, Any]:
    """Delete a custom business-scoped field definition."""
    from google.cloud import bigquery

    if str(data.get("password", "")) != "54321":
        raise ValueError("Administrative password required (use '54321')")
    business_id = str(data.get("business_id", "")).strip()
    if not business_id:
        raise ValueError("Select a business before removing a custom field")
    field_key = str(data.get("field_key", "")).strip()
    if not field_key:
        raise ValueError("Choose a custom field to remove")

    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.field_catalogs"

    lookup_query = (
        f"SELECT field_id, label, is_custom, business_id FROM `{table_ref}` WHERE slug = @slug AND business_id = @business_id LIMIT 1"
    )
    lookup_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("slug", "STRING", field_key),
            bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
        ]
    )
    matches = list(client.query(lookup_query, job_config=lookup_config).result())
    if not matches:
        raise ValueError("Custom field was not found for this business")
    row = matches[0]
    if not row["is_custom"]:
        raise ValueError("Standard fields are built into the platform and cannot be removed")

    delete_query = f"DELETE FROM `{table_ref}` WHERE field_id = @field_id"
    delete_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("field_id", "STRING", row["field_id"])]
    )
    client.query(delete_query, job_config=delete_config).result()
    invalidate_cache()
    return {"deleted": True, "field_key": field_key, "label": row["label"]}
