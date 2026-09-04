from __future__ import annotations

import base64
from functools import lru_cache
import json
import http.server
import logging
import os
from pathlib import Path
import socketserver
from time import perf_counter
from urllib.parse import urlsplit
import urllib.request
from typing import Any
from uuid import uuid4
import re
from logging.handlers import TimedRotatingFileHandler

from whitespace_tool.source_adapters import api_get_source, csv_source, excel_source, json_source, python_connector_source, xml_source
from whitespace_tool.data_validation import validate_normalized_location, validate_source_row
from whitespace_tool.normalization import normalize_location
from whitespace_tool.models import utc_now_iso
from whitespace_tool.learning import suggest_from_templates
from whitespace_tool.field_registry import load_field_registry
from whitespace_tool.sources.demographics import fetch_bigquery_demographics, resolve_bigquery_connection
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, build_table_rows, clear_dataset_tables, push_to_bigquery
from whitespace_tool.storage_config import load_dotenv, load_storage_config


SUPPORTED_SOURCE_TYPES = {"csv", "excel", "json", "xml", "api_get_json", "python_editor"}
MINIMUM_US_ZIP_REFERENCE_ROWS = 30000
MAX_REMOTE_SOURCE_BYTES = 25 * 1024 * 1024


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("whitespace_tool.workflow")
    if logger.handlers:
        return logger
    log_dir = Path(os.environ.get("MAPPER_LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        log_dir / "mapper.log",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
        utc=True,
    )
    handler.setFormatter(logging.Formatter("%(asctime)sZ %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


LOGGER = _build_logger()
ZIP_REFERENCE_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
load_dotenv()


def _json_response(handler: http.server.BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def authenticate(data: dict[str, Any]) -> dict[str, bool]:
    expected_user = os.environ.get("WORKFLOW_LOGIN_USER", "admin")
    expected_password = os.environ.get("WORKFLOW_LOGIN_PASSWORD", "birdeye")
    valid = data.get("username", "") == expected_user and data.get("password", "") == expected_password
    if not valid:
        raise ValueError("Invalid username or password.")
    return {"authenticated": True}


def preview_source(payload: dict[str, Any]) -> dict[str, Any]:
    source_type = payload["source_type"]
    record_path = payload.get("record_path") or None
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type: {source_type}")
    if source_type == "api_get_json":
        return api_get_source.preview_url(
            payload["api_url"],
            record_path,
            payload.get("headers"),
            payload.get("query_params"),
            payload.get("auth"),
        )
    if source_type == "python_editor":
        content = base64.b64decode(payload["content_base64"])
        return python_connector_source.preview(content, record_path)

    file_name = payload.get("file_name", "")
    content = base64.b64decode(payload["content_base64"])
    if source_type == "csv":
        return csv_source.preview(content, record_path)
    if source_type == "json":
        return json_source.preview(content, record_path)
    if source_type == "xml":
        return xml_source.preview(content, record_path)
    if source_type == "excel":
        return excel_source.preview(content, record_path, file_name)
    raise ValueError(f"Unsupported source_type: {source_type}")


def source_sheets(payload: dict[str, Any]) -> dict[str, Any]:
    content = base64.b64decode(payload["content_base64"])
    file_name = payload.get("file_name", "")
    return {"sheets": excel_source.list_sheets(content, file_name)}


def fetch_public_source(payload: dict[str, Any]) -> dict[str, str]:
    url = str(payload.get("url", "")).strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source URL must be a public HTTP or HTTPS URL")
    request = urllib.request.Request(url, headers={"User-Agent": "CompetitiveWhitespaceTool/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read(MAX_REMOTE_SOURCE_BYTES + 1)
        file_name = Path(parsed.path).name or "remote_source"
    if len(content) > MAX_REMOTE_SOURCE_BYTES:
        raise ValueError("Remote source exceeds the 25 MB limit")
    return {"content_base64": base64.b64encode(content).decode("ascii"), "file_name": file_name}


def predefined_templates() -> dict[str, Any]:
    template_index_path = Path("config/predefined_brand_templates.json")
    with template_index_path.open("r", encoding="utf-8") as handle:
        templates = json.load(handle)
    for template in templates:
        with Path(template["template_path"]).open("r", encoding="utf-8") as handle:
            mapper = json.load(handle)
        template["mapper"] = {
            "brand": template["brand"],
            "source_name": template["source_name"],
            "source_type": template["source_type"],
            "record_path": template.get("record_path", mapper.get("record_path", "")),
            "fields": mapper.get("fields", {}),
        }
    return {"templates": templates}


def mapper_targets_with_status() -> dict[str, Any]:
    try:
        return {"fields": field_catalog(), "source": "bigquery"}
    except Exception as exc:
        LOGGER.exception("field_catalog_fallback error=%s", exc)
        return {
            "fields": load_field_registry(),
            "source": "local_registry",
            "warning": (
                "BigQuery field catalog is unavailable, so local default fields were loaded. "
                f"Storage error: {exc}"
            ),
        }


def mapper_targets() -> list[dict[str, Any]]:
    return mapper_targets_with_status()["fields"]


def field_catalog() -> list[dict[str, Any]]:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_dataset(client, project_id, dataset_id)
    table_ref = f"{project_id}.{dataset_id}.field_catalogs"
    schema = [bigquery.SchemaField(field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")) for field in TABLE_SCHEMAS["field_catalogs"]]
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
            client.query(f"INSERT INTO `{table_ref}` (field_id, business_id, slug, label, table_name, field_name, data_type, required, hints, aliases, is_custom, created_at, updated_at) SELECT field_id, NULL, slug, label, table_name, field_name, data_type, required, hints, aliases, is_custom, created_at, updated_at FROM `{legacy_ref}`").result()
    rows = [dict(row) for row in client.query(f"SELECT * FROM `{table_ref}` ORDER BY is_custom, label").result()]
    if not rows:
        now = utc_now_iso()
        seed = []
        for field in load_field_registry():
            seed.append({
                "field_id": str(uuid4()), "business_id": None,
                "slug": field["key"], "label": field["label"], "table_name": field["table"], "field_name": field["field"],
                "data_type": field["type"], "required": field.get("required", False), "hints": json.dumps(field.get("hints", [])),
                "aliases": json.dumps([]), "is_custom": False, "created_at": now, "updated_at": now,
            })
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
    from google.cloud import bigquery

    if str(data.get("password", "")) != "54321":
        raise ValueError("Administrative password required")
    field_key = str(data.get("field_key", "")).strip()
    alias = str(data.get("alias", "")).strip()
    if not field_key or not alias:
        raise ValueError("Standard field and source label are required")
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
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
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("slug", "STRING", field_key), bigquery.ScalarQueryParameter("aliases", "JSON", aliases)])
    client.query(query, job_config=config).result()
    return {"field_key": field_key, "alias": alias}


def create_custom_field(data: dict[str, Any]) -> dict[str, Any]:
    label = str(data.get("label", "")).strip()
    if not label:
        raise ValueError("Field label is required")
    if str(data.get("password", "")) != "54321":
        raise ValueError("Administrative password required")
    business_id = str(data.get("business_id", "")).strip()
    if not business_id:
        raise ValueError("Select a business before adding a custom field")
    slug = re.sub(r"[^a-z0-9]+", "_", str(data.get("slug") or label.lower())).strip("_")
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    catalog = field_catalog()
    if any(row["key"] == slug and row.get("business_id") in {None, business_id} for row in catalog):
        raise ValueError("A field with this slug already exists")
    table_ref = f"{project_id}.{dataset_id}.field_catalogs"
    now = utc_now_iso()
    field = {"field_id": str(uuid4()), "business_id": business_id, "slug": slug, "label": label, "table_name": "listings", "field_name": slug, "data_type": data.get("type", "string"), "required": False, "hints": json.dumps([slug]), "aliases": json.dumps([]), "is_custom": True, "created_at": now, "updated_at": now}
    errors = client.insert_rows_json(table_ref, [field])
    if errors:
        raise RuntimeError(f"Custom field could not be saved: {errors}")
    return {"field": {"key": slug, "label": label, "table": "listings", "field": slug, "type": field["data_type"], "required": False, "hints": [slug], "is_custom": True}}


REQUIRED_MAPPER_FIELDS = {"name", "address", "city", "state", "postal_code"}
REQUIRED_LOCATION_VALUES = ("name", "address", "city", "state", "postal_code")


def validate_mapper(mapper: dict[str, Any], source_fields: list[str], rows: list[dict[str, Any]]) -> list[str]:
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
    secret_keys = {"token", "password", "key_value", "credentials_json"}

    def scrub(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {child_key: scrub(child, child_key) for child_key, child in value.items() if child_key not in secret_keys}
        if isinstance(value, list):
            return [scrub(child) for child in value]
        return value

    return scrub(mapper)


def _warehouse_settings() -> tuple[str, str, str | None]:
    storage_config = load_storage_config(os.environ.get("WORKFLOW_STORAGE_CONFIG", "config/connections/storage.json"))
    if not storage_config.get("project_id") or not storage_config.get("bronze_dataset_id"):
        raise ValueError("Storage project and dataset are missing from the configuration")
    return storage_config["project_id"], storage_config["bronze_dataset_id"], storage_config.get("credentials_json")


def _load_mapped_zip_demographics(zip_codes: set[str]) -> dict[str, Any]:
    config_path = Path(os.environ.get("WORKFLOW_CONFIG", "config/demo.json"))
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    source = config.get("demographics_source", {})
    if source.get("type") != "bigquery" or not zip_codes:
        return {}
    project_id, credentials_json = resolve_bigquery_connection(source, {"_config_dir": str(config_path.parent)})
    quoted_zips = ", ".join(f"'{zip_code}'" for zip_code in sorted(zip_codes))
    query = f"SELECT * FROM ({source['query'].rstrip(';')}) AS public_zips WHERE zip_code IN ({quoted_zips})"
    LOGGER.info("zip_lookup_started source=%s zip_count=%d", source.get("name", "public_demographics"), len(zip_codes))
    demographics = fetch_bigquery_demographics(
        project_id, query, source.get("name", "public_demographics"), credentials_json
    )
    LOGGER.info("zip_lookup_succeeded requested=%d matched=%d", len(zip_codes), len(demographics))
    return demographics


def prepare_zipcodes() -> dict[str, Any]:
    from google.cloud import bigquery

    started_at = perf_counter()
    project_id, dataset_id, credentials_json = _warehouse_settings()
    cache_key = (project_id, dataset_id)
    cached = ZIP_REFERENCE_CACHE.get(cache_key)
    if cached:
        LOGGER.info("zip_reference_timing phase=cache_hit elapsed_ms=%.1f", (perf_counter() - started_at) * 1000)
        return dict(cached)
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.us_zipcodes"
    metadata_started_at = perf_counter()
    _ensure_dataset(client, project_id, dataset_id)
    try:
        existing = client.get_table(table_ref)
        row_count = existing.num_rows or 0
        LOGGER.info("zip_reference_timing phase=metadata_check elapsed_ms=%.1f rows=%d", (perf_counter() - metadata_started_at) * 1000, row_count)
        if row_count >= MINIMUM_US_ZIP_REFERENCE_ROWS:
            LOGGER.info("zip_reference_ready table=%s rows=%d", table_ref, row_count)
            result = {"status": "ready", "rows": int(row_count), "loaded": False}
            ZIP_REFERENCE_CACHE[cache_key] = result
            LOGGER.info("zip_reference_timing phase=ready_total elapsed_ms=%.1f", (perf_counter() - started_at) * 1000)
            return dict(result)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise

    config_path = Path(os.environ.get("WORKFLOW_CONFIG", "config/demo.json"))
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    source = config.get("demographics_source", {})
    source_project_id, source_credentials_json = resolve_bigquery_connection(source, {"_config_dir": str(config_path.parent)})
    LOGGER.info("zip_reference_load_started table=%s", table_ref)
    query_started_at = perf_counter()
    demographics = fetch_bigquery_demographics(source_project_id, source["query"], source.get("name", "public_demographics"), source_credentials_json)
    LOGGER.info("zip_reference_timing phase=source_query elapsed_ms=%.1f rows=%d", (perf_counter() - query_started_at) * 1000, len(demographics))
    rows = {"us_zipcodes": build_table_rows([], demographics)["us_zipcodes"]}
    load_started_at = perf_counter()
    push_to_bigquery(project_id, dataset_id, rows, credentials_json, write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    LOGGER.info("zip_reference_timing phase=table_load elapsed_ms=%.1f rows=%d", (perf_counter() - load_started_at) * 1000, len(rows["us_zipcodes"]))
    LOGGER.info("zip_reference_load_succeeded table=%s rows=%d", table_ref, len(rows["us_zipcodes"]))
    result = {"status": "ready", "rows": len(rows["us_zipcodes"]), "loaded": True}
    ZIP_REFERENCE_CACHE[cache_key] = result
    LOGGER.info("zip_reference_timing phase=rebuild_total elapsed_ms=%.1f", (perf_counter() - started_at) * 1000)
    return dict(result)


@lru_cache(maxsize=8)
def _bigquery_client(project_id: str, credentials_json: str | None):
    from google.cloud import bigquery
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(credentials_json) if credentials_json else None
    return bigquery.Client(project=project_id, credentials=credentials)


def _ensure_dataset(client: Any, project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery

    client.create_dataset(bigquery.Dataset(f"{project_id}.{dataset_id}"), exists_ok=True)


def test_storage_connection() -> dict[str, Any]:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_dataset(client, project_id, dataset_id)
    probe = list(client.query("SELECT 1 AS ok").result())
    if not probe or probe[0]["ok"] != 1:
        raise RuntimeError("BigQuery probe query did not return the expected result")
    return {
        "ok": True,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "dataset": f"{project_id}.{dataset_id}",
        "credentials": "service_account" if credentials_json else "application_default",
    }


def _ensure_businesses_table(client: Any, project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery

    table_ref = f"{project_id}.{dataset_id}.businesses"
    _ensure_dataset(client, project_id, dataset_id)
    try:
        existing = client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        schema = [
            bigquery.SchemaField(
                field["name"], field["type"], mode=field["mode"],
                default_value_expression=field.get("default"),
            )
            for field in TABLE_SCHEMAS["businesses"]
        ]
        client.create_table(bigquery.Table(table_ref, schema=schema))
        return
    existing_names = {field.name for field in existing.schema}
    required_names = {field["name"] for field in TABLE_SCHEMAS["businesses"]}
    if not required_names.issubset(existing_names):
        LOGGER.warning("legacy_brands_table_detected table=%s columns=%s; recreating_empty_table", table_ref, sorted(existing_names))
        client.delete_table(table_ref, not_found_ok=True)
        schema = [
            bigquery.SchemaField(
                field["name"], field["type"], mode=field["mode"],
                default_value_expression=field.get("default"),
            )
            for field in TABLE_SCHEMAS["businesses"]
        ]
        client.create_table(bigquery.Table(table_ref, schema=schema))


def list_brands(search: str = "") -> dict[str, Any]:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    query = f"SELECT business_id, name, slug, website_url, status FROM `{project_id}.{dataset_id}.businesses` WHERE is_deleted IS NOT TRUE AND (@search = '' OR LOWER(name) LIKE CONCAT('%', LOWER(@search), '%')) ORDER BY name LIMIT 100"
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("search", "STRING", search)])
    return {"brands": [dict(row) for row in client.query(query, job_config=config).result()]}


def ensure_source_type(source_type: str) -> str:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_dataset(client, project_id, dataset_id)
    table_ref = f"{project_id}.{dataset_id}.source_types"
    schema = [bigquery.SchemaField(field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")) for field in TABLE_SCHEMAS["source_types"]]
    try:
        client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(bigquery.Table(table_ref, schema=schema))
    query = f"SELECT source_type_id FROM `{table_ref}` WHERE name = @name LIMIT 1"
    params = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("name", "STRING", source_type)])
    found = list(client.query(query, job_config=params).result())
    if found:
        return found[0]["source_type_id"]
    insert = f"INSERT INTO `{table_ref}` (name, data_format, created_at) VALUES (@name, @format, CURRENT_TIMESTAMP())"
    params = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("name", "STRING", source_type), bigquery.ScalarQueryParameter("format", "JSON", json.dumps({"type": source_type}))])
    client.query(insert, job_config=params).result()
    found = list(client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("name", "STRING", source_type)])).result())
    if not found:
        raise RuntimeError("Source type was created but its database-generated ID was not returned")
    return found[0]["source_type_id"]


def create_brand(data: dict[str, Any]) -> dict[str, Any]:
    from google.cloud import bigquery

    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Brand name is required")
    slug = str(data.get("slug") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    query = f"""
    INSERT INTO `{project_id}.{dataset_id}.businesses`
      (name, slug, description, logo_url, website_url, status, created_at, updated_at, meta_title, meta_description, country_of_origin)
    VALUES (@name, @slug, @description, @logo_url, @website_url, @status, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), @meta_title, @meta_description, @country_of_origin)
    """
    params = [
        bigquery.ScalarQueryParameter("name", "STRING", name), bigquery.ScalarQueryParameter("slug", "STRING", slug),
        bigquery.ScalarQueryParameter("description", "STRING", data.get("description")), bigquery.ScalarQueryParameter("logo_url", "STRING", data.get("logo_url")),
        bigquery.ScalarQueryParameter("website_url", "STRING", data.get("website_url")), bigquery.ScalarQueryParameter("status", "STRING", data.get("status") or "active"),
        bigquery.ScalarQueryParameter("meta_title", "STRING", data.get("meta_title")), bigquery.ScalarQueryParameter("meta_description", "STRING", data.get("meta_description")),
        bigquery.ScalarQueryParameter("country_of_origin", "STRING", data.get("country_of_origin")),
    ]
    client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    lookup = f"SELECT business_id, name, slug, website_url, status FROM `{project_id}.{dataset_id}.businesses` WHERE is_deleted IS NOT TRUE AND slug = @slug ORDER BY created_at DESC LIMIT 1"
    result = list(client.query(lookup, job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("slug", "STRING", slug)])).result())
    if not result:
        raise RuntimeError("Brand was created but its database-generated ID could not be read back")
    return {"brand": dict(result[0])}


def learn_mappings(data: dict[str, Any]) -> dict[str, Any]:
    from google.cloud import bigquery

    source_type = str(data.get("source_type", ""))
    source_fields = data.get("source_fields", [])
    if not source_type or not isinstance(source_fields, list):
        raise ValueError("source_type and source_fields are required")
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.workflow_templates"
    try:
        templates = [dict(row) for row in client.query(f"SELECT components FROM `{table_ref}` ORDER BY updated_at DESC LIMIT 500").result()]
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"suggestions": {}}
        raise
    return {"suggestions": suggest_from_templates(templates, source_fields, source_type)}


def list_templates(search: str = "", business_id: str = "", source_type_id: str = "") -> dict[str, Any]:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    query = f"SELECT workflow_template_id, business_id, name, components, created_at, updated_at FROM `{project_id}.{dataset_id}.workflow_templates` WHERE (@search = '' OR LOWER(name) LIKE CONCAT('%', LOWER(@search), '%')) AND (@business_id = '' OR business_id = @business_id) AND (@source_type_id = '' OR JSON_VALUE(components, '$.source_type_id') = @source_type_id OR JSON_VALUE(components, '$.mapper.source_type_id') = @source_type_id) ORDER BY updated_at DESC LIMIT 100"
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("search", "STRING", search), bigquery.ScalarQueryParameter("business_id", "STRING", business_id), bigquery.ScalarQueryParameter("source_type_id", "STRING", source_type_id)])
    templates = []
    for row in client.query(query, job_config=config).result():
        item = dict(row)
        if hasattr(item.get("created_at"), "isoformat"):
            item["created_at"] = item["created_at"].isoformat()
        if hasattr(item.get("updated_at"), "isoformat"):
            item["updated_at"] = item["updated_at"].isoformat()
        if isinstance(item.get("components"), str):
            item["components"] = json.loads(item["components"])
        templates.append(item)
    return {"templates": templates}


def list_source_types() -> dict[str, Any]:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    try:
        rows = client.query(f"SELECT source_type_id, name FROM `{project_id}.{dataset_id}.source_types` ORDER BY name").result()
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"source_types": []}
        raise
    return {"source_types": [dict(row) for row in rows]}


def _csv_param(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def reporting_summary(params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    from google.cloud import bigquery

    params = params or {}
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    source_table = os.environ.get("REPORTING_LISTINGS_TABLE") or f"{project_id}.{dataset_id}.listings"
    if source_table.count(".") == 1:
        source_table = f"{project_id}.{source_table}"
    table_ref = f"`{source_table}`"
    zip_ref = f"`{project_id}.{dataset_id}.us_zipcodes`"
    main_brands = _csv_param(params.get("main_brands", [""])[0])
    competitor_brands = _csv_param(params.get("competitor_brands", [""])[0])
    selected_brands = sorted(set(main_brands + competitor_brands))
    state_filter = str(params.get("state", [""])[0]).strip().upper()
    county_filter = str(params.get("county", [""])[0]).strip()
    city_filter = str(params.get("city", [""])[0]).strip()
    zip_filter = str(params.get("zip", [""])[0]).strip()
    query_params: list[Any] = [
        bigquery.ArrayQueryParameter("selected_brands", "STRING", selected_brands),
        bigquery.ArrayQueryParameter("main_brands", "STRING", main_brands),
        bigquery.ArrayQueryParameter("competitor_brands", "STRING", competitor_brands),
        bigquery.ScalarQueryParameter("state", "STRING", state_filter),
        bigquery.ScalarQueryParameter("county", "STRING", county_filter),
        bigquery.ScalarQueryParameter("city", "STRING", city_filter),
        bigquery.ScalarQueryParameter("zip", "STRING", zip_filter),
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    base_cte = f"""
    WITH base AS (
      SELECT
        l.*,
        COALESCE(b.name, l.business_id) AS brand,
        z.county,
        z.population
      FROM {table_ref} l
      LEFT JOIN `{project_id}.{dataset_id}.businesses` b
        ON l.business_id = b.business_id
      LEFT JOIN {zip_ref} z
        ON l.zip_code = z.zip_code
      WHERE l.is_deleted IS NOT TRUE
        AND (ARRAY_LENGTH(@selected_brands) = 0 OR COALESCE(b.name, l.business_id) IN UNNEST(@selected_brands))
        AND (@state = '' OR UPPER(COALESCE(l.state_code, '')) = @state)
        AND (@county = '' OR LOWER(COALESCE(z.county, '')) = LOWER(@county))
        AND (@city = '' OR LOWER(COALESCE(l.city_name, '')) = LOWER(@city))
        AND (@zip = '' OR COALESCE(l.zip_code, '') = @zip)
    )
    """

    totals_query = base_cte + """
    SELECT
      COUNT(*) AS total_locations,
      COUNT(DISTINCT brand) AS total_brands,
      COUNT(DISTINCT state_code) AS total_states,
      COUNT(DISTINCT city_name) AS total_cities,
      COUNT(DISTINCT zip_code) AS total_zips,
      MAX(last_observed_at) AS last_updated
    FROM base
    """
    top_states_query = base_cte + """
    SELECT
      COALESCE(state_code, '') AS state,
      COUNT(*) AS locations,
      COUNT(DISTINCT city_name) AS cities,
      COUNT(DISTINCT brand) AS brands
    FROM base
    GROUP BY state
    ORDER BY locations DESC
    LIMIT 10
    """
    top_cities_query = base_cte + """
    SELECT
      COALESCE(city_name, '') AS city,
      COALESCE(state_code, '') AS state,
      COALESCE(county, '') AS county,
      COUNT(*) AS locations
    FROM base
    GROUP BY city, state, county
    ORDER BY locations DESC
    LIMIT 10
    """
    brand_query = base_cte + """
    SELECT
      brand,
      COUNT(*) AS locations,
      COUNT(DISTINCT state_code) AS states,
      COUNT(DISTINCT county) AS counties,
      COUNT(DISTINCT city_name) AS cities,
      COUNT(DISTINCT zip_code) AS zips
    FROM base
    GROUP BY brand
    ORDER BY locations DESC
    LIMIT 10
    """
    filter_options_query = f"""
    WITH base AS (
      SELECT COALESCE(b.name, l.business_id) AS brand, l.state_code, l.city_name, l.zip_code, z.county
      FROM {table_ref} l
      LEFT JOIN `{project_id}.{dataset_id}.businesses` b ON l.business_id = b.business_id
      LEFT JOIN {zip_ref} z ON l.zip_code = z.zip_code
      WHERE l.is_deleted IS NOT TRUE
    )
    SELECT
      ARRAY_AGG(DISTINCT brand IGNORE NULLS ORDER BY brand) AS brands,
      ARRAY_AGG(DISTINCT state_code IGNORE NULLS ORDER BY state_code) AS states,
      ARRAY_AGG(DISTINCT county IGNORE NULLS ORDER BY county LIMIT 500) AS counties,
      ARRAY_AGG(DISTINCT city_name IGNORE NULLS ORDER BY city_name LIMIT 500) AS cities,
      ARRAY_AGG(DISTINCT zip_code IGNORE NULLS ORDER BY zip_code LIMIT 500) AS zips
    FROM base
    """
    gap_query = base_cte + """
    , grouped AS (
      SELECT
        state_code AS state,
        county,
        city_name AS city,
        zip_code,
        ARRAY_AGG(DISTINCT brand IGNORE NULLS ORDER BY brand) AS brands_present,
        COUNTIF(brand IN UNNEST(@main_brands)) AS main_locations,
        COUNTIF(brand IN UNNEST(@competitor_brands)) AS competitor_locations
      FROM base
      GROUP BY state, county, city, zip_code
    )
    SELECT
      state,
      county,
      city,
      zip_code,
      competitor_locations,
      ARRAY_TO_STRING(brands_present, ', ') AS brands_present
    FROM grouped
    WHERE ARRAY_LENGTH(@main_brands) > 0
      AND ARRAY_LENGTH(@competitor_brands) > 0
      AND main_locations = 0
      AND competitor_locations > 0
    ORDER BY competitor_locations DESC, state, county, city, zip_code
    LIMIT 100
    """
    sample_query = base_cte + """
    SELECT
      name,
      address,
      city_name AS city,
      state_code AS state,
      county,
      zip_code,
      phone_number,
      latitude,
      longitude,
      country,
      last_observed_at
    FROM base
    ORDER BY last_observed_at DESC, name
    LIMIT 10
    """

    try:
        totals = dict(next(iter(client.query(totals_query, job_config=job_config).result())))
        top_states = [dict(row) for row in client.query(top_states_query, job_config=job_config).result()]
        top_cities = [dict(row) for row in client.query(top_cities_query, job_config=job_config).result()]
        brands = [dict(row) for row in client.query(brand_query, job_config=job_config).result()]
        gaps = [dict(row) for row in client.query(gap_query, job_config=job_config).result()]
        filter_options = dict(next(iter(client.query(filter_options_query).result())))
        sample_records = [dict(row) for row in client.query(sample_query, job_config=job_config).result()]
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {
                "source_table": source_table,
                "totals": {},
                "top_states": [],
                "top_cities": [],
                "brands": [],
                "gaps": [],
                "filter_options": {"brands": [], "states": [], "counties": [], "cities": [], "zips": []},
                "states_without_locations": [],
                "sample_records": [],
                "message": "No reporting data found yet. Save mapped listings first.",
            }
        raise

    state_codes = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
        "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
        "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
        "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    }
    present_states = {row["state"] for row in top_states if row.get("state")}
    all_present_query = base_cte + "SELECT DISTINCT state_code AS state FROM base"
    present_states.update(row["state"] for row in client.query(all_present_query, job_config=job_config).result() if row.get("state"))
    states_without_locations = sorted(state_codes - present_states)

    for row in [totals, *top_states, *top_cities, *brands, *gaps, *sample_records]:
        for key, value in list(row.items()):
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat()
    filter_options = {key: list(value or []) for key, value in filter_options.items()}

    return {
        "source_table": source_table,
        "filters": {
            "main_brands": main_brands,
            "competitor_brands": competitor_brands,
            "state": state_filter,
            "county": county_filter,
            "city": city_filter,
            "zip": zip_filter,
        },
        "filter_options": filter_options,
        "totals": totals,
        "top_states": top_states,
        "top_cities": top_cities,
        "brands": brands,
        "gaps": gaps,
        "states_without_locations": states_without_locations,
        "sample_records": sample_records,
    }


def save_template_version(data: dict[str, Any]) -> dict[str, Any]:
    from google.cloud import bigquery

    template_id = str(data.get("workflow_template_id", "")).strip()
    components = data.get("components")
    if not template_id or not isinstance(components, dict):
        raise ValueError("workflow_template_id and components are required")
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.workflow_templates"
    query = f"UPDATE `{table_ref}` SET archived_components = components, components = @components, updated_at = CURRENT_TIMESTAMP() WHERE workflow_template_id = @template_id"
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("template_id", "STRING", template_id), bigquery.ScalarQueryParameter("components", "JSON", json.dumps(components, sort_keys=True))])
    client.query(query, job_config=config).result()
    return {"workflow_template_id": template_id, "updated": True}


def list_rejected(event_id: str = "") -> dict[str, Any]:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    query = f"SELECT event_id, business_id, source_type_id, row_number, errors, raw_record FROM `{project_id}.{dataset_id}.error_listings` WHERE is_deleted IS NOT TRUE AND (@event_id = '' OR event_id = @event_id) ORDER BY event_id, row_number LIMIT 500"
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("event_id", "STRING", event_id)])
    try:
        result_rows = client.query(query, job_config=config).result()
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"records": []}
        raise
    records = []
    for row in result_rows:
        item = dict(row)
        for key in ("errors", "raw_record"):
            if isinstance(item.get(key), str):
                try:
                    item[key] = json.loads(item[key])
                except ValueError:
                    pass
        records.append(item)
    return {"records": records}


def count_error_listings(business_id: str = "") -> int:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    query = f"SELECT COUNT(*) AS total FROM `{project_id}.{dataset_id}.error_listings` WHERE is_deleted IS NOT TRUE AND (@business_id = '' OR business_id = @business_id)"
    from google.cloud import bigquery
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("business_id", "STRING", business_id)])
    try:
        return int(next(iter(client.query(query, job_config=config).result()))["total"])
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return 0
        raise


def reprocess_rejected(data: dict[str, Any]) -> dict[str, Any]:
    event_id = str(data.get("event_id", "")).strip()
    mapper = data.get("mapper")
    if not event_id or not isinstance(mapper, dict):
        raise ValueError("event_id and mapper are required")
    records = list_rejected(event_id)["records"]
    selected_numbers = {int(value) for value in data.get("row_numbers", [])}
    rows = [record["raw_record"] for record in records if not selected_numbers or record["row_number"] in selected_numbers]
    if not rows:
        raise ValueError("No rejected records were found for reprocessing")
    source_fields = sorted({path for path in mapper.get("fields", {}).values() if path})
    return save_mapper({"mapper": mapper, "rows": rows, "source_fields": source_fields})


def save_mapper(payload: dict[str, Any]) -> dict[str, Any]:
    mapper = payload.get("mapper")
    rows = payload.get("rows")
    source_fields = payload.get("source_fields", [])
    if not isinstance(mapper, dict) or not isinstance(rows, list) or not isinstance(source_fields, list):
        raise ValueError("mapper, rows, and source_fields are required")
    LOGGER.info(
        "save_started brand=%r source_name=%r source_type=%r rows=%d source_fields=%d",
        mapper.get("brand", ""),
        mapper.get("source_name", ""),
        mapper.get("source_type", "unknown"),
        len(rows),
        len(source_fields),
    )
    errors = validate_mapper(mapper, source_fields, rows)
    if errors:
        raise ValueError(f"Mapper validation failed: {', '.join(errors)}")

    source_name = str(mapper["source_name"]).strip()
    source_type_id = str(mapper.get("source_type_id", "")).strip() or ensure_source_type(str(mapper.get("source_type", "unknown")))
    field_definitions = field_catalog()
    business_id = str(mapper.get("business_id", "")).strip()
    if not business_id:
        raise ValueError("Select an existing business or create a new business before saving")
    event_id = str(payload.get("event_id") or uuid4().hex)
    mapper["business_id"] = business_id
    mapper["source_type_id"] = source_type_id
    locations = []
    error_listings = []
    for index, row in enumerate(rows):
        row_errors = validate_source_row(row, mapper)
        location = normalize_location(row, mapper, source_name, index)
        if location is None:
            row_errors.append({"field": "required_location", "reason": "missing brand or ZIP Code"})
        elif any(not str(getattr(location, field) or "").strip() for field in REQUIRED_LOCATION_VALUES):
            row_errors.append({"field": "required_location", "reason": "missing mandatory value"})
        if location is not None:
            row_errors.extend(validate_normalized_location(location, field_definitions))
        if row_errors:
            error_listings.append({
                "event_id": event_id,
                "business_id": business_id,
                "source_type_id": source_type_id,
                "row_number": index + 1,
                "errors": json.dumps(row_errors, sort_keys=True),
                "raw_record": json.dumps(row, sort_keys=True),
                "is_deleted": False,
                "deleted_on": None,
            })
        elif location is not None:
            locations.append(location)
    project_id, dataset_id, credentials_json = _warehouse_settings()

    mapper_id = f"mapper_{uuid4().hex}"
    config_json = _scrub_mapper(mapper)
    demographics = _load_mapped_zip_demographics({location.zip5 for location in locations})
    rows_by_table = build_table_rows(locations, demographics)
    rows_by_table["businesses"] = []
    for record in error_listings:
        record["source_type_id"] = source_type_id
    rows_by_table["source_types"] = []
    rows_by_table["workflow_templates"] = [{
        "workflow_template_id": str(uuid4()),
        "business_id": business_id, "name": source_name,
        "components": json.dumps({"mapper": mapper, "source_type_id": source_type_id}, sort_keys=True),
        "archived_components": None, "created_at": utc_now_iso(), "updated_at": utc_now_iso(),
    }]
    rows_by_table["error_listings"] = error_listings
    push_to_bigquery(project_id, dataset_id, rows_by_table, credentials_json)
    LOGGER.info(
        "save_succeeded mapper_id=%s dataset=%s mapped_rows=%d mapped_fields=%d",
        mapper_id,
        f"{project_id}.{dataset_id}",
        len(locations),
        len(mapper["fields"]),
    )
    return {"event_id": event_id, "mapper_id": mapper_id, "total_rows": len(rows), "mapped_rows": len(locations), "error_listings": len(error_listings), "field_count": len(mapper["fields"]), "dataset": f"{project_id}.{dataset_id}"}


def clear_saved_data() -> dict[str, Any]:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    clear_result = clear_dataset_tables(project_id, dataset_id, credentials_json)
    deleted = clear_result["soft_deleted_tables"]
    truncated = clear_result["truncated_tables"]
    ZIP_REFERENCE_CACHE.pop((project_id, dataset_id), None)
    return {
        "dataset": f"{project_id}.{dataset_id}",
        "deleted_tables": deleted,
        "deleted_count": len(deleted),
        "truncated_tables": truncated,
        "truncated_count": len(truncated),
    }


def make_handler(ui_dir: Path):
    class MapperHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ui_dir), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:
            if self.path == "/api/schema":
                result = mapper_targets_with_status()
                _json_response(self, 200, {"targets": result["fields"], "source": result["source"], "warning": result.get("warning")})
                return
            if self.path == "/api/field-registry":
                result = mapper_targets_with_status()
                _json_response(self, 200, result)
                return
            if self.path == "/api/prepare":
                try:
                    _json_response(self, 200, prepare_zipcodes())
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path == "/api/predefined-templates":
                try:
                    _json_response(self, 200, predefined_templates())
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path == "/api/storage/test":
                try:
                    _json_response(self, 200, test_storage_connection())
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/brands"):
                from urllib.parse import parse_qs, urlsplit
                search = parse_qs(urlsplit(self.path).query).get("search", [""])[0]
                try:
                    _json_response(self, 200, list_brands(search))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/templates"):
                from urllib.parse import parse_qs, urlsplit
                params = parse_qs(urlsplit(self.path).query)
                search = params.get("search", [""])[0]
                business_id = params.get("business_id", [""])[0]
                source_type_id = params.get("source_type_id", [""])[0]
                try:
                    _json_response(self, 200, list_templates(search, business_id, source_type_id))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path == "/api/source-types":
                try:
                    _json_response(self, 200, list_source_types())
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path == "/api/reporting":
                from urllib.parse import parse_qs, urlsplit
                try:
                    _json_response(self, 200, reporting_summary(parse_qs(urlsplit(self.path).query)))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return

            if self.path.startswith("/api/rejected"):
                from urllib.parse import parse_qs, urlsplit
                event_id = parse_qs(urlsplit(self.path).query).get("event_id", [""])[0]
                try:
                    _json_response(self, 200, list_rejected(event_id))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/error-listings/count"):
                from urllib.parse import parse_qs, urlsplit
                business_id = parse_qs(urlsplit(self.path).query).get("business_id", [""])[0]
                try:
                    _json_response(self, 200, {"count": count_error_listings(business_id)})
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            super().do_GET()

        def do_POST(self) -> None:
            if self.path not in {"/api/login", "/api/preview", "/api/source-url", "/api/sheets", "/api/save", "/api/clear", "/api/brands", "/api/learning", "/api/reprocess", "/api/field-alias", "/api/custom-field", "/api/templates/save"}:
                _json_response(self, 404, {"error": "Not found"})
                return
            request_id = uuid4().hex
            try:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                payload["event_id"] = request_id
                LOGGER.info("request_started request_id=%s endpoint=%s content_length=%d", request_id, self.path, length)
                if self.path == "/api/login":
                    _json_response(self, 200, authenticate(payload))
                elif self.path == "/api/source-url":
                    _json_response(self, 200, fetch_public_source(payload))
                elif self.path == "/api/sheets":
                    _json_response(self, 200, source_sheets(payload))
                elif self.path == "/api/save":
                    _json_response(self, 200, save_mapper(payload))
                elif self.path == "/api/clear":
                    _json_response(self, 200, clear_saved_data())
                elif self.path == "/api/brands":
                    _json_response(self, 200, create_brand(payload))
                elif self.path == "/api/learning":
                    _json_response(self, 200, learn_mappings(payload))
                elif self.path == "/api/reprocess":
                    _json_response(self, 200, reprocess_rejected(payload))
                elif self.path == "/api/field-alias":
                    _json_response(self, 200, add_field_alias(payload))
                elif self.path == "/api/custom-field":
                    _json_response(self, 200, create_custom_field(payload))
                elif self.path == "/api/templates/save":
                    _json_response(self, 200, save_template_version(payload))
                else:
                    _json_response(self, 200, preview_source(payload))
            except Exception as exc:
                LOGGER.exception("request_failed request_id=%s endpoint=%s error=%s", request_id, self.path, exc)
                _json_response(self, 400, {"error": str(exc), "request_id": request_id})

    return MapperHandler


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    ui_dir = Path("ui").resolve()
    handler = make_handler(ui_dir)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), handler) as httpd:
        print(f"Workflow UI running at http://{host}:{port}/")
        httpd.serve_forever()
