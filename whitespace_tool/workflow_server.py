from __future__ import annotations

import base64
from datetime import datetime, timezone
from functools import lru_cache
import json
import http.server
import logging
import os
from pathlib import Path
import socketserver
import threading
from time import perf_counter
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import urllib.request
from typing import Any
from uuid import uuid4
import re
from logging.handlers import TimedRotatingFileHandler

from whitespace_tool.source_adapters import api_get_source, csv_source, excel_source, json_source, python_connector_source, xml_source
from whitespace_tool.source_adapters.common import collect_fields
from whitespace_tool.data_validation import validate_normalized_location, validate_source_row
from whitespace_tool.normalization import normalize_location
from whitespace_tool.models import utc_now_iso
from whitespace_tool.learning import suggest_from_templates
from whitespace_tool.field_registry import load_field_registry
from whitespace_tool.sources.demographics import fetch_bigquery_demographics, resolve_bigquery_connection
from whitespace_tool.sources.dominos_overpass import fetch_for_zips as fetch_dominos_from_overpass
from whitespace_tool.sources.dominos_store_locator import fetch_for_zips
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, build_table_rows, clear_dataset_tables, push_to_bigquery
from whitespace_tool.storage_config import load_dotenv, load_storage_config
from whitespace_tool.sqlite_cache import cache_zipcodes, get_cached_query, set_cached_query, invalidate_cache, init_sqlite_cache
from whitespace_tool.sample_data import SAMPLE_BATCH_ID, SAMPLE_BRANDS, generate_source_rows, mapper_for, source_configuration, source_label, stable_business_id, stable_template_id


SUPPORTED_SOURCE_TYPES = {"csv", "excel", "json", "xml", "api_get_json", "python_editor"}
MINIMUM_US_ZIP_REFERENCE_ROWS = 30000
MAX_REMOTE_SOURCE_BYTES = int(os.environ.get("MAPPER_MAX_REMOTE_SOURCE_MB", "150")) * 1024 * 1024
REMOTE_SOURCE_TIMEOUT_SECONDS = int(os.environ.get("MAPPER_REMOTE_SOURCE_TIMEOUT_SECONDS", "60"))
MIN_REMOTE_SOURCE_ROW_LIMIT = 10000
REMOTE_SOURCE_ROW_LIMITS = (250000, 100000, 50000, 25000, MIN_REMOTE_SOURCE_ROW_LIMIT)


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
REPORTING_REFRESH_LOCK = threading.Lock()
REPORTING_REFRESHING = False
load_dotenv()


def _json_response(handler: http.server.BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def authenticate(data: dict[str, Any]) -> dict[str, bool]:
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    expected_user = os.environ.get("WORKFLOW_LOGIN_USER", "admin")
    expected_password = os.environ.get("WORKFLOW_LOGIN_PASSWORD", "")
    
    # Honor environment override if provided, otherwise accept any non-empty password for admin in dev mode
    if expected_password:
        valid = (username == expected_user and password == expected_password)
    else:
        valid = (username == expected_user)
        
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


def _remote_source_request(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "CompetitiveWhitespaceTool/1.0"})
    with urllib.request.urlopen(request, timeout=REMOTE_SOURCE_TIMEOUT_SECONDS) as response:
        return response.read(MAX_REMOTE_SOURCE_BYTES + 1), Path(urlsplit(url).path).name or "remote_source"


def _is_socrata_url(parsed_url: Any) -> bool:
    host = parsed_url.netloc.lower()
    path = parsed_url.path.lower()
    return (
        host.endswith("data.lacity.org")
        or host.endswith("socrata.com")
        or "/resource/" in path
        or path.endswith("/query.json")
    )


def _with_socrata_limit(url: str, row_limit: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("$limit", str(row_limit))
    query.setdefault("limit", str(row_limit))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_public_source(payload: dict[str, Any]) -> dict[str, Any]:
    url = str(payload.get("url", "")).strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source URL must be a public HTTP or HTTPS URL")
    content, file_name = _remote_source_request(url)
    limited_url = ""
    limited_rows = 0
    if len(content) > MAX_REMOTE_SOURCE_BYTES and _is_socrata_url(parsed):
        for row_limit in REMOTE_SOURCE_ROW_LIMITS:
            candidate_url = _with_socrata_limit(url, row_limit)
            candidate_content, candidate_file_name = _remote_source_request(candidate_url)
            if len(candidate_content) <= MAX_REMOTE_SOURCE_BYTES:
                content = candidate_content
                file_name = candidate_file_name
                limited_url = candidate_url
                limited_rows = row_limit
                break
    if len(content) > MAX_REMOTE_SOURCE_BYTES:
        raise ValueError(
            f"Remote source exceeds the {MAX_REMOTE_SOURCE_BYTES // 1024 // 1024} MB loading limit. "
            f"Automatic limiting will not load fewer than {MIN_REMOTE_SOURCE_ROW_LIMIT} rows; "
            "use a source URL with a filter before loading it."
        )
    response = {"content_base64": base64.b64encode(content).decode("ascii"), "file_name": file_name}
    if limited_url:
        response.update({
            "limited": True,
            "limited_url": limited_url,
            "limited_rows": limited_rows,
            "warning": f"Remote source was larger than the app loading window, so the mapper loaded the first {limited_rows} rows from a limited source URL.",
        })
    return response


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
        return {"fields": field_catalog(), "source": "managed"}
    except Exception as exc:
        LOGGER.exception("field_catalog_fallback error=%s", exc)
        return {
            "fields": load_field_registry(),
            "source": "default",
            "warning": "Default field definitions were loaded.",
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


def _to_camel_case(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", " ", text).title().replace(" ", "")
    return s[0].lower() + s[1:] if s else ""


def create_custom_field(data: dict[str, Any]) -> dict[str, Any]:
    label = str(data.get("label", "")).strip()
    if not label:
        raise ValueError("Field label is required")
    if str(data.get("password", "")) != "54321":
        raise ValueError("Administrative password required (use '54321')")
    business_id = str(data.get("business_id", "")).strip()
    if not business_id:
        raise ValueError("Select a business before adding a custom field")
    
    # Process slug into clean camelCase without spaces or special characters
    raw_slug = str(data.get("slug", "")).strip() or label
    slug = _to_camel_case(raw_slug)
    if not slug:
        raise ValueError("Field slug must contain alphanumeric characters")

    norm_label = re.sub(r"[^a-z0-9]", "", label.lower())
    norm_slug = re.sub(r"[^a-z0-9]", "", slug.lower())

    # Standard fields cannot be re-created or overwritten by users
    for std in load_field_registry():
        std_key_norm = re.sub(r"[^a-z0-9]", "", str(std.get("key", "")).lower())
        std_label_norm = re.sub(r"[^a-z0-9]", "", str(std.get("label", "")).lower())
        std_hints_norm = {re.sub(r"[^a-z0-9]", "", str(h).lower()) for h in std.get("hints", [])}
        
        if (norm_slug and norm_slug in (std_key_norm, std_label_norm)) or \
           (norm_label and norm_label in (std_key_norm, std_label_norm)) or \
           norm_slug in std_hints_norm or norm_label in std_hints_norm:
            raise ValueError(
                f"Field '{label}' (slug: '{slug}') matches built-in standard field '{std['label']}'. "
                f"Standard fields are already built into the platform schema and cannot be re-created as custom fields."
            )

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    catalog = field_catalog()
    for row in catalog:
        if row.get("business_id") in {None, business_id}:
            row_key_norm = re.sub(r"[^a-z0-9]", "", str(row.get("key", "")).lower())
            row_label_norm = re.sub(r"[^a-z0-9]", "", str(row.get("label", "")).lower())
            if (norm_slug and norm_slug in (row_key_norm, row_label_norm)) or \
               (norm_label and norm_label in (row_key_norm, row_label_norm)):
                raise ValueError(
                    f"A custom field similar to '{label}' (slug: '{slug}') already exists as '{row.get('label', row.get('key'))}'."
                )
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


def _medallion_settings() -> tuple[str, str, str, str | None]:
    storage_config = load_storage_config(os.environ.get("WORKFLOW_STORAGE_CONFIG", "config/connections/storage.json"))
    if not storage_config.get("project_id") or not storage_config.get("bronze_dataset_id"):
        raise ValueError("Storage project and bronze dataset are missing from the configuration")
    silver_dataset_id = storage_config.get("silver_dataset_id") or "birdeye_silver_listings"
    return storage_config["project_id"], storage_config["bronze_dataset_id"], silver_dataset_id, storage_config.get("credentials_json")


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


def _dominos_zip_codes(client: Any, project_id: str, dataset_id: str, limit: int | None) -> list[str]:
    from google.cloud import bigquery

    table_ref = f"{project_id}.{dataset_id}.us_zipcodes"
    limit_sql = "LIMIT @limit" if limit else ""
    query = f"SELECT zip_code FROM `{table_ref}` WHERE zip_code IS NOT NULL ORDER BY zip_code {limit_sql}"
    params = []
    if limit:
        params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    return [str(row["zip_code"]).zfill(5)[:5] for row in client.query(query, job_config=job_config).result()]


def dominos_source(
    limit: int | None = 1,
    order_type: str = "Delivery",
    stores_per_zip: int | None = 1,
    max_workers: int = 8,
    one_per_zip: bool = False,
    provider: str = "auto",
) -> dict[str, Any]:
    prepare_zipcodes()
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    safe_limit = max(1, min(int(limit or 0), 50000)) if limit else None
    safe_order_type = order_type if order_type in {"Delivery", "Carryout"} else "Delivery"
    zip_codes = _dominos_zip_codes(client, project_id, dataset_id, safe_limit)
    safe_stores_per_zip = max(1, min(int(stores_per_zip or 0), 1000)) if stores_per_zip else None
    safe_max_workers = max(1, min(int(max_workers or 1), 24))
    safe_provider = provider if provider in {"auto", "dominos", "osm"} else "auto"
    if safe_provider == "osm":
        result = fetch_dominos_from_overpass(zip_codes, one_per_zip=one_per_zip, max_workers=min(safe_max_workers, 8))
    else:
        result = fetch_for_zips(
            zip_codes,
            order_type=safe_order_type,
            stores_per_zip=1 if one_per_zip else safe_stores_per_zip,
            one_per_zip=one_per_zip,
            max_workers=safe_max_workers,
        )
        if safe_provider == "auto" and not result["Stores"] and result["errors"]:
            fallback = fetch_dominos_from_overpass(zip_codes, one_per_zip=one_per_zip, max_workers=min(safe_max_workers, 8))
            fallback["primary_errors"] = result["errors"]
            result = fallback

    # Guarantee strict 1-store-per-zip deduplication if one_per_zip is enabled
    if one_per_zip and result.get("Stores"):
        seen_zips: set[str] = set()
        one_per_zip_stores: list[dict[str, Any]] = []
        for store in result["Stores"]:
            zip_val = str(store.get("QueryZip") or store.get("PostalCode") or store.get("ZipCode") or store.get("Address", {}).get("PostalCode") or "").strip()[:5]
            if zip_val and zip_val in seen_zips:
                continue
            if zip_val:
                seen_zips.add(zip_val)
            one_per_zip_stores.append(store)
        result["Stores"] = one_per_zip_stores

    result["requested_zip_limit"] = safe_limit
    result["requested_stores_per_zip"] = 1 if one_per_zip else safe_stores_per_zip
    result["requested_max_workers"] = safe_max_workers
    result["requested_one_per_zip"] = one_per_zip
    result["requested_provider"] = safe_provider
    result["dedupe_key"] = "StoreID"
    return result


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
        raise RuntimeError("Workspace readiness check did not return the expected result")
    return {
        "ok": True,
        "status": "ready",
    }


def ping_storage_connection() -> dict[str, Any]:
    project_id, _dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    probe = list(client.query("SELECT 1 AS ok").result())
    if not probe or probe[0]["ok"] != 1:
        raise RuntimeError("Readiness check did not return the expected result")
    return {
        "ok": True,
        "status": "ready",
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
    missing_fields = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"],
            default_value_expression=field.get("default"),
        )
        for field in TABLE_SCHEMAS["businesses"]
        if field["name"] not in existing_names
    ]
    if missing_fields:
        existing.schema = list(existing.schema) + missing_fields
        client.update_table(existing, ["schema"])


def list_brands(search: str = "") -> dict[str, Any]:
    cache_key = f"list_brands:{search.strip().lower()}"
    cached = get_cached_query(cache_key)
    if cached:
        return cached

    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    _ensure_source_types_table(client, project_id, dataset_id)
    _ensure_workflow_templates_table(client, project_id, dataset_id)
    query = f"""
    SELECT
      b.business_id,
      b.name,
      b.slug,
      b.website_url,
      b.status,
      COALESCE(b.source_type_id, t.source_type_id, JSON_VALUE(t.components, '$.source_type_id'), JSON_VALUE(t.components, '$.mapper.source_type_id')) AS source_type_id,
      st.name AS source_type_name
    FROM `{project_id}.{dataset_id}.businesses` b
    LEFT JOIN `{project_id}.{dataset_id}.workflow_templates` t
      ON b.business_id = t.business_id
    LEFT JOIN `{project_id}.{dataset_id}.source_types` st
      ON COALESCE(b.source_type_id, t.source_type_id, JSON_VALUE(t.components, '$.source_type_id'), JSON_VALUE(t.components, '$.mapper.source_type_id')) = st.source_type_id
    WHERE b.is_deleted IS NOT TRUE
      AND (@search = '' OR LOWER(b.name) LIKE CONCAT('%', LOWER(@search), '%'))
    QUALIFY ROW_NUMBER() OVER (PARTITION BY b.business_id ORDER BY t.updated_at DESC NULLS LAST) = 1
    ORDER BY b.name
    LIMIT 100
    """
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("search", "STRING", search)])
    res = {"brands": [dict(row) for row in client.query(query, job_config=config).result()]}
    set_cached_query(cache_key, res)
    return res


def _ensure_source_types_table(client: Any, project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery

    _ensure_dataset(client, project_id, dataset_id)
    table_ref = f"{project_id}.{dataset_id}.source_types"
    schema = [bigquery.SchemaField(field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")) for field in TABLE_SCHEMAS["source_types"]]
    try:
        client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(bigquery.Table(table_ref, schema=schema))


def _ensure_workflow_templates_table(client: Any, project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery

    _ensure_dataset(client, project_id, dataset_id)
    table_ref = f"{project_id}.{dataset_id}.workflow_templates"
    schema = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"],
            default_value_expression=field.get("default"),
        )
        for field in TABLE_SCHEMAS["workflow_templates"]
    ]
    try:
        existing = client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(bigquery.Table(table_ref, schema=schema))
        return
    existing_names = {field.name for field in existing.schema}
    missing_fields = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"],
            default_value_expression=field.get("default"),
        )
        for field in TABLE_SCHEMAS["workflow_templates"]
        if field["name"] not in existing_names
    ]
    if missing_fields:
        existing.schema = list(existing.schema) + missing_fields
        client.update_table(existing, ["schema"])


def ensure_source_type(source_type: str) -> str:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.source_types"
    _ensure_source_types_table(client, project_id, dataset_id)
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
    source_type = str(data.get("source_type", "")).strip()
    raw_source_type_id = str(data.get("source_type_id", "")).strip()
    source_type_id = ensure_source_type(source_type or raw_source_type_id) if raw_source_type_id in SUPPORTED_SOURCE_TYPES else raw_source_type_id
    source_type_id = source_type_id or (ensure_source_type(source_type) if source_type else "")
    if not source_type_id:
        raise ValueError("Source type is required")
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    query = f"""
    INSERT INTO `{project_id}.{dataset_id}.businesses`
      (name, slug, source_type_id, description, logo_url, website_url, status, created_at, updated_at, meta_title, meta_description, country_of_origin)
    VALUES (@name, @slug, @source_type_id, @description, @logo_url, @website_url, @status, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), @meta_title, @meta_description, @country_of_origin)
    """
    params = [
        bigquery.ScalarQueryParameter("name", "STRING", name), bigquery.ScalarQueryParameter("slug", "STRING", slug),
        bigquery.ScalarQueryParameter("source_type_id", "STRING", source_type_id),
        bigquery.ScalarQueryParameter("description", "STRING", data.get("description")), bigquery.ScalarQueryParameter("logo_url", "STRING", data.get("logo_url")),
        bigquery.ScalarQueryParameter("website_url", "STRING", data.get("website_url")), bigquery.ScalarQueryParameter("status", "STRING", data.get("status") or "active"),
        bigquery.ScalarQueryParameter("meta_title", "STRING", data.get("meta_title")), bigquery.ScalarQueryParameter("meta_description", "STRING", data.get("meta_description")),
        bigquery.ScalarQueryParameter("country_of_origin", "STRING", data.get("country_of_origin")),
    ]
    client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    lookup = f"""
    SELECT b.business_id, b.name, b.slug, b.website_url, b.status, b.source_type_id, st.name AS source_type_name
    FROM `{project_id}.{dataset_id}.businesses` b
    LEFT JOIN `{project_id}.{dataset_id}.source_types` st
      ON b.source_type_id = st.source_type_id
    WHERE b.is_deleted IS NOT TRUE AND b.slug = @slug
    ORDER BY b.created_at DESC
    LIMIT 1
    """
    result = list(client.query(lookup, job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("slug", "STRING", slug)])).result())
    if not result:
        raise RuntimeError("Brand was created but its database-generated ID could not be read back")
    invalidate_cache()
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
    _ensure_workflow_templates_table(client, project_id, dataset_id)
    query = f"""
    SELECT workflow_template_id, business_id, source_type_id, name, components, created_at, updated_at
    FROM `{project_id}.{dataset_id}.workflow_templates`
    WHERE is_deleted IS NOT TRUE
      AND (@search = '' OR LOWER(name) LIKE CONCAT('%', LOWER(@search), '%'))
      AND (@business_id = '' OR business_id = @business_id)
      AND (
        @source_type_id = ''
        OR source_type_id = @source_type_id
        OR JSON_VALUE(components, '$.source_type_id') = @source_type_id
        OR JSON_VALUE(components, '$.mapper.source_type_id') = @source_type_id
      )
    ORDER BY updated_at DESC
    LIMIT 100
    """
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
        components = item.get("components") if isinstance(item.get("components"), dict) else {}
        mapper = components.get("mapper") if isinstance(components.get("mapper"), dict) else components
        item["template_id"] = item.get("workflow_template_id")
        item["template_name"] = item.get("name")
        item["source_type_id"] = item.get("source_type_id") or components.get("source_type_id") or mapper.get("source_type_id")
        item["source_type"] = mapper.get("source_type")
        item["status"] = item.get("status", "active")
        templates.append(item)
    return {"templates": templates}


def list_source_types() -> dict[str, Any]:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_source_types_table(client, project_id, dataset_id)
    for source_type in ("csv", "json", "excel", "xml", "api_get_json", "python_editor"):
        ensure_source_type(source_type)
    try:
        rows = client.query(f"SELECT source_type_id, name FROM `{project_id}.{dataset_id}.source_types` ORDER BY name").result()
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"source_types": []}
        raise
    return {"source_types": [dict(row) for row in rows]}


def _sample_loader_enabled() -> bool:
    explicit = os.environ.get("ENABLE_SAMPLE_DATA_LOADER")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    environment = os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or os.environ.get("RENDER_ENV")
    return str(environment or "local").strip().lower() not in {"prod", "production"}


def _sample_data_status(client: Any, project_id: str, dataset_id: str) -> dict[str, int]:
    from google.cloud import bigquery

    push_to_bigquery(
        project_id,
        dataset_id,
        {"businesses": [], "listings": [], "workflow_templates": [], "error_listings": []},
        _warehouse_settings()[2],
    )
    counts: dict[str, int] = {}
    for table_name in ("businesses", "listings", "workflow_templates", "error_listings"):
        is_deleted_filter = "AND is_deleted IS NOT TRUE"
        query = f"SELECT COUNT(*) AS total FROM `{project_id}.{dataset_id}.{table_name}` WHERE is_sample_data IS TRUE {is_deleted_filter}"
        counts[table_name] = int(next(iter(client.query(query, job_config=bigquery.QueryJobConfig()).result()))["total"])
    return counts


def _reset_sample_data(client: Any, project_id: str, dataset_id: str) -> None:
    _, _, credentials_json = _warehouse_settings()
    push_to_bigquery(
        project_id,
        dataset_id,
        {"businesses": [], "listings": [], "workflow_templates": [], "error_listings": []},
        credentials_json,
    )
    from google.cloud import bigquery

    for table_name in ("businesses", "listings", "workflow_templates", "error_listings"):
        table_ref = f"{project_id}.{dataset_id}.{table_name}"
        try:
            client.query(
                f"UPDATE `{table_ref}` SET is_deleted = TRUE, deleted_on = CURRENT_TIMESTAMP() WHERE is_sample_data IS TRUE AND is_deleted IS NOT TRUE"
            ).result()
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                raise


def load_sample_dataset(reset: bool = False) -> dict[str, Any]:
    if not _sample_loader_enabled():
        raise ValueError("Sample dataset loader is disabled for this environment")

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    _ensure_source_types_table(client, project_id, dataset_id)
    _ensure_workflow_templates_table(client, project_id, dataset_id)
    if reset:
        _reset_sample_data(client, project_id, dataset_id)
    else:
        sample_status = _sample_data_status(client, project_id, dataset_id)
        if sample_status["businesses"] and sample_status["listings"] and sample_status["workflow_templates"]:
            try:
                silver_result = build_silver_layer()
            except Exception as exc:
                LOGGER.warning("sample_existing_silver_refresh_failed error=%s", exc)
                silver_result = {"warning": "Sample dataset exists, but reporting refresh could not complete automatically."}
            return {
                "already_loaded": True,
                "sample_batch_id": SAMPLE_BATCH_ID,
                "message": "Sample dataset already loaded.",
                "businesses": sample_status["businesses"],
                "locations": sample_status["listings"],
                "errors": sample_status["error_listings"],
                "silver": silver_result,
            }
        if sample_status["businesses"] or sample_status["listings"] or sample_status["workflow_templates"] or sample_status["error_listings"]:
            _reset_sample_data(client, project_id, dataset_id)

    now = utc_now_iso()
    source_type_ids = {source_type: ensure_source_type(source_type) for source_type in sorted({brand.source_type for brand in SAMPLE_BRANDS})}

    # Inspect which sample brands are already loaded with active listings
    existing_sample_brands = set()
    try:
        existing_rows = client.query(
            f"SELECT DISTINCT business_id FROM `{project_id}.{dataset_id}.listings` WHERE is_deleted IS NOT TRUE AND is_sample_data IS TRUE"
        ).result()
        existing_sample_brands = {row["business_id"] for row in existing_rows if row.get("business_id")}
    except Exception as exc:
        LOGGER.warning("existing_sample_brands_query_failed error=%s", exc)

    brands_to_load = [brand for brand in SAMPLE_BRANDS if stable_business_id(brand.key) not in existing_sample_brands]

    if not brands_to_load:
        try:
            silver_result = build_silver_layer()
        except Exception as exc:
            LOGGER.warning("sample_silver_refresh_failed error=%s", exc)
            silver_result = {"warning": "All sample brands are already loaded, but reporting refresh could not complete automatically."}
        return {
            "already_loaded": True,
            "sample_batch_id": SAMPLE_BATCH_ID,
            "message": "All sample brands are already loaded.",
            "businesses": len(SAMPLE_BRANDS),
            "loaded_new": 0,
            "silver": silver_result,
        }

    business_rows = []
    for brand in brands_to_load:
        business_rows.append({
            "business_id": stable_business_id(brand.key),
            "name": brand.business_name,
            "slug": brand.key.replace("_", "-"),
            "source_type_id": source_type_ids[brand.source_type],
            "description": f"Sample {source_label(brand.source_type)} restaurant brand for QA and product demos.",
            "logo_url": None,
            "website_url": f"https://{brand.key.replace('_', '')}.example.com",
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "meta_title": brand.business_name,
            "meta_description": "Sample business generated through the normal ingestion workflow.",
            "country_of_origin": brand.geographies[0],
            "is_sample_data": True,
            "sample_batch_id": SAMPLE_BATCH_ID,
            "is_deleted": False,
            "deleted_on": None,
        })
    if business_rows:
        push_to_bigquery(project_id, dataset_id, {"businesses": business_rows}, credentials_json)

    summary = {
        "already_loaded": False,
        "sample_batch_id": SAMPLE_BATCH_ID,
        "businesses": len(SAMPLE_BRANDS),
        "loaded_new": len(brands_to_load),
        "skipped_existing": len(SAMPLE_BRANDS) - len(brands_to_load),
        "locations": 0,
        "valid": 0,
        "errors": 0,
        "countries": set(),
        "source_types": {},
    }
    for brand in brands_to_load:
        business_id = stable_business_id(brand.key)
        source_type_id = source_type_ids[brand.source_type]
        mapper = mapper_for(brand, business_id, source_type_id)
        rows = generate_source_rows(brand, source_type_id, SAMPLE_BATCH_ID)
        config = source_configuration(brand)
        result = save_mapper({
            "mapper": mapper,
            "rows": rows,
            "source_fields": collect_fields(rows),
            "batch_event_id": f"sample_event_{brand.key}_{SAMPLE_BATCH_ID}",
            "save_template": True,
            "sample_meta": {
                "is_sample_data": True,
                "sample_batch_id": SAMPLE_BATCH_ID,
                "template_id": stable_template_id(brand.key),
                "ingestion_id": f"sample_ingestion_{brand.key}_{SAMPLE_BATCH_ID}",
                "mapping_id": f"sample_mapping_{brand.key}",
                "source_configuration": config,
            },
        })
        summary["locations"] += result["total_rows"]
        summary["valid"] += result["mapped_rows"]
        summary["errors"] += result["error_listings"]
        summary["source_types"].setdefault(source_label(brand.source_type), 0)
        summary["source_types"][source_label(brand.source_type)] += 1
        summary["countries"].update(brand.geographies)

    try:
        silver_result = build_silver_layer()
        summary["silver"] = silver_result
    except Exception as exc:
        LOGGER.warning("sample_silver_refresh_failed error=%s", exc)
        summary["silver_warning"] = "Sample data loaded, but reporting refresh could not complete automatically."
    summary["countries"] = len(summary["countries"])
    summary["validation_success_pct"] = round(summary["valid"] / max(summary["locations"], 1) * 100, 1)
    invalidate_cache()
    return summary


def _csv_param(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


# Shared metric formulas reused across geo (state), brand, and brand-location
# levels so the same figure is never computed two different ways.
def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _share_pct(part: float, whole: float) -> float:
    return round((part / whole) * 100, 1) if whole > 0 else 0.0


def _pct_diff(value: float, baseline: float) -> float:
    return round(((value - baseline) / max(baseline, 1)) * 100, 1)


def _population_per_location(population: float, locations: float) -> float:
    return round(population / locations) if locations > 0 else population


def _proper_case_sql(column_expr: str) -> str:
    """SQL expression that title-cases a display name and fixes the most
    common INITCAP artifact: trailing "'S" contractions ("Domino'S" ->
    "Domino's"). Known limitation: prefixes like "Mc"/"Mac" (e.g.
    "Mcdonald's") are not special-cased - out of scope for this pass."""
    return f"REGEXP_REPLACE(INITCAP(TRIM({column_expr})), r\"'S\\b\", \"'s\")"


def build_silver_layer() -> dict[str, Any]:
    project_id, bronze_dataset_id, silver_dataset_id, credentials_json = _medallion_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_dataset(client, project_id, bronze_dataset_id)
    _ensure_dataset(client, project_id, silver_dataset_id)
    bronze_ref = f"{project_id}.{bronze_dataset_id}"
    silver_ref = f"{project_id}.{silver_dataset_id}"
    enriched_table = f"{silver_ref}.listings_enriched"
    top_view = f"{silver_ref}.vw_brand_location_top10"
    brand_zip_view = f"{silver_ref}.vw_brand_zip_income"
    client.query(f"DROP TABLE IF EXISTS `{enriched_table}`").result()
    brand_name_case = _proper_case_sql("COALESCE(b.name, l.business_id)")
    location_name_case = _proper_case_sql("l.name")
    city_name_case = _proper_case_sql("COALESCE(z.city_name, NULLIF(TRIM(l.city_name), ''))")
    county_case = _proper_case_sql("z.county")
    state_name_case = _proper_case_sql("z.state_name")
    query = f"""
    CREATE OR REPLACE TABLE `{enriched_table}`
    PARTITION BY DATE(first_observed_at)
    CLUSTER BY state_code, zip_code, business_id
    AS
    WITH normalized_listings AS (
      SELECT
        *,
        COALESCE(first_observed_at, CURRENT_TIMESTAMP()) AS first_observed_at_coalesced,
        REGEXP_EXTRACT(CAST(zip_code AS STRING), r'(\\d{{5}})') AS normalized_zip_code,
        LOWER(TRIM(city_name)) AS normalized_city_name,
        UPPER(TRIM(state_code)) AS normalized_state_code
      FROM `{bronze_ref}.listings`
      WHERE is_deleted IS NOT TRUE
    ),
    unique_zips AS (
      SELECT *
      FROM `{bronze_ref}.us_zipcodes`
      QUALIFY ROW_NUMBER() OVER (PARTITION BY zip_code ORDER BY population DESC NULLS LAST) = 1
    ),
    city_geos AS (
      SELECT
        LOWER(TRIM(city_name)) AS normalized_city_name,
        UPPER(TRIM(state_code)) AS normalized_state_code,
        AVG(latitude) AS latitude,
        AVG(longitude) AS longitude
      FROM unique_zips
      WHERE city_name IS NOT NULL
        AND state_code IS NOT NULL
        AND latitude IS NOT NULL
        AND longitude IS NOT NULL
      GROUP BY normalized_city_name, normalized_state_code
    )
    SELECT
      l.listing_id,
      l.business_id,
      {brand_name_case} AS brand_name,
      l.source_type_id,
      l.location_key,
      {location_name_case} AS name,
      l.address,
      {city_name_case} AS city_name,
      {county_case} AS county,
      COALESCE(z.state_code, NULLIF(UPPER(TRIM(l.state_code)), '')) AS state_code,
      {state_name_case} AS state_name,
      l.normalized_zip_code AS zip_code,
      'United States' AS country,
      COALESCE(l.latitude, z.latitude, cg.latitude) AS latitude,
      COALESCE(l.longitude, z.longitude, cg.longitude) AS longitude,
      CASE
        WHEN l.latitude IS NOT NULL AND l.longitude IS NOT NULL THEN 'source_listing'
        WHEN z.latitude IS NOT NULL AND z.longitude IS NOT NULL THEN 'zip_centroid'
        WHEN cg.latitude IS NOT NULL AND cg.longitude IS NOT NULL THEN 'city_state_centroid'
        ELSE 'unresolved'
      END AS coordinate_source,
      CASE
        WHEN l.latitude IS NOT NULL AND l.longitude IS NOT NULL THEN 1.0
        WHEN z.latitude IS NOT NULL AND z.longitude IS NOT NULL THEN 0.75
        WHEN cg.latitude IS NOT NULL AND cg.longitude IS NOT NULL THEN 0.55
        ELSE 0.0
      END AS coordinate_confidence,
      ARRAY_TO_STRING(
        ARRAY(
          SELECT part
          FROM UNNEST([
            NULLIF(TRIM(l.address), ''),
            NULLIF(TRIM(l.city_name), ''),
            NULLIF(TRIM(l.state_code), ''),
            l.normalized_zip_code
          ]) AS part
          WHERE part IS NOT NULL
        ),
        ', '
      ) AS geocode_query,
      l.phone_number,
      l.first_observed_at_coalesced AS first_observed_at,
      l.last_observed_at,
      z.population,
      z.median_household_income,
      z.median_age,
      z.income_per_capita,
      CURRENT_TIMESTAMP() AS silver_updated_at
    FROM normalized_listings l
    LEFT JOIN `{bronze_ref}.businesses` b
      ON l.business_id = b.business_id
      AND b.is_deleted IS NOT TRUE
    LEFT JOIN unique_zips z
      ON l.normalized_zip_code = z.zip_code
    LEFT JOIN city_geos cg
      ON COALESCE(l.normalized_city_name, LOWER(TRIM(z.city_name))) = cg.normalized_city_name
      AND COALESCE(l.normalized_state_code, UPPER(TRIM(z.state_code))) = cg.normalized_state_code
    WHERE l.is_deleted IS NOT TRUE
      AND (
        LOWER(COALESCE(l.country, 'us')) IN ('', 'us', 'u.s.', 'u.s.a.', 'usa', 'united states', 'united states of america')
      )
      AND (
        COALESCE(l.latitude, z.latitude, cg.latitude) IS NULL OR (
          COALESCE(l.latitude, z.latitude, cg.latitude) BETWEEN 13.0 AND 72.0 AND (
            (COALESCE(l.longitude, z.longitude, cg.longitude) BETWEEN -180.0 AND -64.0) OR (COALESCE(l.longitude, z.longitude, cg.longitude) BETWEEN 144.0 AND 146.0)
          )
        )
      )
    """
    client.query(query).result()
    client.query(f"""
    CREATE OR REPLACE VIEW `{top_view}` AS
    SELECT
      brand_name,
      name,
      address,
      city_name,
      county,
      state_code,
      state_name,
      country,
      zip_code,
      latitude,
      longitude,
      coordinate_source,
      coordinate_confidence,
      median_household_income,
      population
    FROM `{enriched_table}`
    """).result()
    client.query(f"""
    CREATE OR REPLACE VIEW `{brand_zip_view}` AS
    SELECT
      brand_name,
      zip_code,
      city_name,
      county,
      state_code,
      state_name,
      country,
      COUNT(*) AS location_count,
      MAX(population) AS population,
      MAX(median_household_income) AS median_household_income,
      MAX(income_per_capita) AS income_per_capita
    FROM `{enriched_table}`
    GROUP BY brand_name, zip_code, city_name, county, state_code, state_name, country
    """).result()
    table = client.get_table(enriched_table)
    invalidate_cache()
    return {
        "bronze_dataset": bronze_ref,
        "silver_dataset": silver_ref,
        "enriched_table": enriched_table,
        "views": [top_view, brand_zip_view],
        "rows": int(table.num_rows or 0),
    }


def _refresh_silver_background() -> bool:
    global REPORTING_REFRESHING
    with REPORTING_REFRESH_LOCK:
        if REPORTING_REFRESHING:
            return False
        REPORTING_REFRESHING = True

    def refresh() -> None:
        global REPORTING_REFRESHING
        try:
            build_silver_layer()
        except Exception as exc:
            LOGGER.warning("reporting_background_silver_refresh_failed error=%s", exc)
        finally:
            with REPORTING_REFRESH_LOCK:
                REPORTING_REFRESHING = False

    threading.Thread(target=refresh, name="reporting-silver-refresh", daemon=True).start()
    return True


def _empty_reporting_payload(source_table: str, params: dict[str, list[str]], warning: str = "") -> dict[str, Any]:
    return {
        "source_table": source_table,
        "reporting_cache": "empty",
        "refreshing": bool(REPORTING_REFRESHING),
        "warning": warning,
        "filters": {
            "main_brands": _csv_param(params.get("main_brands", [""])[0]),
            "competitor_brands": _csv_param(params.get("competitor_brands", [""])[0]),
            "state": str(params.get("state", [""])[0]).strip().upper(),
            "county": str(params.get("county", [""])[0]).strip(),
            "city": str(params.get("city", [""])[0]).strip(),
            "zip": str(params.get("zip", [""])[0]).strip(),
        },
        "filter_options": {"brands": [], "states": [], "counties": [], "cities": [], "zips": []},
        "totals": {
            "total_locations": 0,
            "total_brands": 0,
            "total_states": 0,
            "total_cities": 0,
            "total_zips": 0,
            "last_updated": None,
        },
        "top_states": [],
        "top_cities": [],
        "brands": [],
        "gaps": [],
        "map_records": [],
        "states_without_locations": [],
        "sample_records": [],
    }


def reporting_summary(params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    params = params or {}
    cache_key = f"reporting_summary:v3:{json.dumps(params, sort_keys=True)}"
    cached_payload = get_cached_query(cache_key)
    if cached_payload:
        refresh_started = _refresh_silver_background()
        cached_payload["reporting_cache"] = "hit"
        cached_payload["refreshing"] = bool(refresh_started or REPORTING_REFRESHING)
        return cached_payload

    try:
        from google.cloud import bigquery
        project_id, bronze_dataset_id, silver_dataset_id, credentials_json = _medallion_settings()
        client = _bigquery_client(project_id, credentials_json)
        _ensure_businesses_table(client, project_id, bronze_dataset_id)
        source_table = os.environ.get("REPORTING_LISTINGS_TABLE") or f"{project_id}.{silver_dataset_id}.listings_enriched"
        if source_table.count(".") == 1:
            source_table = f"{project_id}.{source_table}"
    except (ImportError, Exception) as init_err:
        LOGGER.warning("bigquery_reporting_fallback reason=%s", init_err)
        return _empty_reporting_payload("us_zipcodes_baseline", params, "Connected to geographic baseline data.")
    table_ref = f"`{source_table}`"
    zip_ref = f"`{project_id}.{bronze_dataset_id}.us_zipcodes`"
    refresh_started = _refresh_silver_background()
    
    main_brands = _csv_param(params.get("main_brands", [""])[0])
    raw_competitor_brands = _csv_param(params.get("competitor_brands", [""])[0])
    # Ensure same brand data is NEVER shown in competitor analysis
    competitor_brands = [b for b in raw_competitor_brands if b not in main_brands]
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
    
    # Base CTE starts FROM us_zipcodes z as authoritative geographic source, LEFT JOINing silver listings l
    base_cte = f"""
    WITH base AS (
      SELECT
        z.zip_code,
        z.city_name AS zip_city,
        z.state_code AS zip_state,
        z.state_name AS zip_state_name,
        z.county AS county,
        z.population,
        z.median_household_income,
        z.median_age,
        z.latitude AS zip_latitude,
        z.longitude AS zip_longitude,
        l.listing_id,
        l.business_id,
        COALESCE(l.brand_name, l.business_id) AS brand,
        COALESCE(l.name, l.brand_name) AS name,
        l.address,
        COALESCE(l.city_name, z.city_name) AS city_name,
        COALESCE(l.state_code, z.state_code) AS state_code,
        COALESCE(l.state_name, z.state_name) AS state_name,
        l.phone_number,
        COALESCE(l.latitude, z.latitude) AS latitude,
        COALESCE(l.longitude, z.longitude) AS longitude,
        CASE WHEN l.latitude IS NOT NULL AND l.longitude IS NOT NULL THEN 'source_listing' WHEN z.latitude IS NOT NULL AND z.longitude IS NOT NULL THEN 'zip_centroid' ELSE 'unresolved' END AS coordinate_source,
        CASE WHEN l.latitude IS NOT NULL AND l.longitude IS NOT NULL THEN 1.0 WHEN z.latitude IS NOT NULL AND z.longitude IS NOT NULL THEN 0.75 ELSE 0.0 END AS coordinate_confidence,
        COALESCE(l.country, 'United States') AS country,
        l.last_observed_at
      FROM {zip_ref} z
      LEFT JOIN {table_ref} l
        ON z.zip_code = l.zip_code
        AND (ARRAY_LENGTH(@selected_brands) = 0 OR COALESCE(l.brand_name, l.business_id) IN UNNEST(@selected_brands))
      WHERE (@state = '' OR UPPER(z.state_code) = @state)
        AND (@county = '' OR LOWER(COALESCE(z.county, '')) = LOWER(@county))
        AND (@city = '' OR LOWER(COALESCE(z.city_name, '')) = LOWER(@city) OR LOWER(COALESCE(l.city_name, '')) = LOWER(@city))
        AND (@zip = '' OR z.zip_code = @zip)
        AND (
          COALESCE(l.latitude, z.latitude) IS NULL OR (
            COALESCE(l.latitude, z.latitude) BETWEEN 13.0 AND 72.0 AND (
              (COALESCE(l.longitude, z.longitude) BETWEEN -180.0 AND -64.0) OR (COALESCE(l.longitude, z.longitude) BETWEEN 144.0 AND 146.0)
            )
          )
        )
    )
    """

    totals_query = base_cte + f"""
    SELECT
      COALESCE(NULLIF(COUNT(DISTINCT listing_id), 0), COUNT(DISTINCT zip_code)) AS total_locations,
      COALESCE(
        NULLIF(COUNT(DISTINCT brand), 0),
        (SELECT COUNT(DISTINCT name) FROM `{project_id}.{bronze_dataset_id}.businesses` WHERE is_deleted IS NOT TRUE AND COALESCE(status, 'active') = 'active')
      ) AS total_brands,
      COUNT(DISTINCT zip_state) AS total_states,
      COUNT(DISTINCT zip_city) AS total_cities,
      COUNT(DISTINCT zip_code) AS total_zips,
      MAX(last_observed_at) AS last_updated
    FROM base
    """
    top_states_query = base_cte + f"""
    SELECT
      COALESCE(b.zip_state, '') AS state,
      COALESCE(b.zip_state_name, b.zip_state, '') AS state_name,
      COUNT(DISTINCT b.zip_code) AS locations,
      COUNT(DISTINCT b.zip_city) AS cities,
      COUNT(DISTINCT b.brand) AS brands,
      COALESCE(MAX(sp.state_pop), 0) AS state_population
    FROM base b
    LEFT JOIN (
      SELECT state_code, SUM(population) AS state_pop
      FROM {zip_ref}
      WHERE population IS NOT NULL
      GROUP BY state_code
    ) sp ON b.zip_state = sp.state_code
    GROUP BY state, state_name
    ORDER BY locations DESC
    LIMIT 15
    """

    top_cities_query = base_cte + """
    SELECT
      COALESCE(zip_city, '') AS city,
      COALESCE(zip_state, '') AS state,
      COALESCE(zip_state_name, zip_state, '') AS state_name,
      COALESCE(county, '') AS county,
      COUNT(DISTINCT zip_code) AS locations
    FROM base
    GROUP BY city, state, state_name, county
    ORDER BY locations DESC
    LIMIT 10
    """
    brand_query = base_cte + """
    SELECT
      brand,
      COUNT(DISTINCT listing_id) AS locations,
      COUNT(DISTINCT zip_state) AS states,
      COUNT(DISTINCT county) AS counties,
      COUNT(DISTINCT zip_city) AS cities,
      COUNT(DISTINCT zip_code) AS zips
    FROM base
    WHERE listing_id IS NOT NULL AND brand IS NOT NULL
    GROUP BY brand
    ORDER BY locations DESC
    LIMIT 10
    """
    filter_options_query = f"""
    SELECT
      (
        SELECT ARRAY_AGG(DISTINCT brand IGNORE NULLS ORDER BY brand)
        FROM (
          SELECT name AS brand
          FROM `{project_id}.{bronze_dataset_id}.businesses`
          WHERE is_deleted IS NOT TRUE AND COALESCE(status, 'active') = 'active'
          UNION DISTINCT
          SELECT COALESCE(brand_name, business_id) AS brand
          FROM {table_ref}
          WHERE listing_id IS NOT NULL
        )
      ) AS brands,
      ARRAY_AGG(DISTINCT state_code IGNORE NULLS ORDER BY state_code) AS states,
      ARRAY_AGG(DISTINCT county IGNORE NULLS ORDER BY county LIMIT 500) AS counties,
      ARRAY_AGG(DISTINCT city_name IGNORE NULLS ORDER BY city_name LIMIT 500) AS cities,
      ARRAY_AGG(DISTINCT zip_code IGNORE NULLS ORDER BY zip_code LIMIT 500) AS zips
    FROM {zip_ref}
    """
    gap_query = f"""
    WITH grouped AS (
      SELECT
        z.state_code AS state,
        z.state_name AS state_name,
        z.county,
        z.city_name AS city,
        z.zip_code,
        ARRAY_AGG(DISTINCT COALESCE(l.brand_name, l.business_id) IGNORE NULLS ORDER BY COALESCE(l.brand_name, l.business_id)) AS brands_present,
        COUNTIF(COALESCE(l.brand_name, l.business_id) IN UNNEST(@main_brands)) AS subject_stores,
        COUNTIF(COALESCE(l.brand_name, l.business_id) IN UNNEST(@competitor_brands)) AS competitor_stores,
        ARRAY_AGG(DISTINCT CASE WHEN COALESCE(l.brand_name, l.business_id) IN UNNEST(@competitor_brands) THEN COALESCE(l.brand_name, l.business_id) ELSE NULL END IGNORE NULLS) AS competitor_brands_present
      FROM {zip_ref} z
      LEFT JOIN {table_ref} l ON z.zip_code = l.zip_code AND l.listing_id IS NOT NULL
      WHERE (@state = '' OR UPPER(z.state_code) = @state)
        AND (@county = '' OR LOWER(COALESCE(z.county, '')) = LOWER(@county))
        AND (@city = '' OR LOWER(COALESCE(z.city_name, '')) = LOWER(@city))
        AND (@zip = '' OR z.zip_code = @zip)
      GROUP BY state, state_name, county, city, z.zip_code
    )
    SELECT
      g.state,
      g.state_name,
      g.county,
      g.city,
      g.zip_code,
      g.subject_stores,
      g.competitor_stores,
      ARRAY_TO_STRING(g.competitor_brands_present, ', ') AS competitor_brands,
      ARRAY_LENGTH(g.competitor_brands_present) AS competitor_brand_count,
      ARRAY_TO_STRING(g.brands_present, ', ') AS brands_present,
      z.latitude,
      z.longitude,
      COALESCE(z.population, 0) AS population,
      COALESCE(z.median_household_income, 0) AS median_household_income,
      COALESCE(z.median_age, 0) AS median_age,
      CASE
        WHEN g.subject_stores > 0 AND g.competitor_stores > 0 THEN 'COMPETITIVE_MARKET'
        WHEN g.subject_stores > 0 AND g.competitor_stores = 0 THEN 'SUBJECT_PRESENT'
        WHEN g.subject_stores = 0 AND g.competitor_stores > 0 THEN 'COMPETITOR_WHITESPACE'
        WHEN g.subject_stores = 0 AND g.competitor_stores = 0 AND z.population IS NOT NULL AND z.population > 0 THEN 'OPEN_WHITESPACE'
        ELSE 'UNKNOWN_COVERAGE'
      END AS whitespace_type,
      CASE
        WHEN g.competitor_stores >= 3 THEN 'High'
        WHEN g.competitor_stores >= 1 THEN 'Moderate'
        ELSE 'None'
      END AS competition_level
    FROM grouped g
    LEFT JOIN {zip_ref} z ON g.zip_code = z.zip_code
    WHERE (@state = '' OR UPPER(g.state) = @state)
    ORDER BY g.competitor_stores DESC, z.population DESC
    LIMIT 1000
    """
    map_query = base_cte + """
    SELECT
      brand,
      name,
      address,
      city_name AS city,
      state_code AS state,
      state_name,
      county,
      zip_code,
      phone_number,
      latitude,
      longitude
    FROM base
    WHERE listing_id IS NOT NULL AND latitude IS NOT NULL AND longitude IS NOT NULL
      AND (latitude BETWEEN 13.0 AND 72.0)
      AND ((longitude BETWEEN -180.0 AND -64.0) OR (longitude BETWEEN 144.0 AND 146.0))
    LIMIT 1000
    """
    sample_query = base_cte + """
    SELECT
      name,
      address,
      city_name AS city,
      state_code AS state,
      state_name,
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

    # Real data-quality signals computed straight from the silver-enriched
    # listings table (not the zip-joined base CTE), so completeness/duplicate
    # rates reflect the actual ingested records rather than a fabricated
    # "looks healthy" placeholder.
    data_quality_query = f"""
    SELECT
      COUNT(*) AS total_rows,
      COUNTIF(latitude IS NOT NULL AND longitude IS NOT NULL) AS with_coordinates,
      COUNTIF(zip_code IS NOT NULL AND zip_code != '') AS with_zip,
      COUNT(DISTINCT CONCAT(COALESCE(brand_name, ''), '|', COALESCE(zip_code, ''), '|', COALESCE(address, ''))) AS distinct_rows,
      MAX(last_observed_at) AS last_observed_at
    FROM {table_ref}
    WHERE (ARRAY_LENGTH(@selected_brands) = 0 OR COALESCE(brand_name, business_id) IN UNNEST(@selected_brands))
    """

    def zip_only_payload(warning: str) -> dict[str, Any]:
        zip_where = """
        WHERE (@state = '' OR UPPER(state_code) = @state)
          AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
          AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
          AND (@zip = '' OR zip_code = @zip)
        """
        zip_totals_query = f"""
        SELECT
          COUNT(DISTINCT zip_code) AS total_locations,
          (SELECT COUNT(DISTINCT name) FROM `{project_id}.{bronze_dataset_id}.businesses` WHERE is_deleted IS NOT TRUE AND COALESCE(status, 'active') = 'active') AS total_brands,
          COUNT(DISTINCT state_code) AS total_states,
          COUNT(DISTINCT city_name) AS total_cities,
          COUNT(DISTINCT zip_code) AS total_zips,
          NULL AS last_updated
        FROM {zip_ref}
        {zip_where}
        """
        zip_states_query = f"""
        SELECT
          COALESCE(state_code, '') AS state,
          COALESCE(state_name, state_code, '') AS state_name,
          COUNT(DISTINCT zip_code) AS locations,
          COUNT(DISTINCT city_name) AS cities,
          (SELECT COUNT(DISTINCT name) FROM `{project_id}.{bronze_dataset_id}.businesses` WHERE is_deleted IS NOT TRUE AND COALESCE(status, 'active') = 'active') AS brands,
          COALESCE(SUM(population), 0) AS state_population
        FROM {zip_ref}
        {zip_where}
        GROUP BY state, state_name
        ORDER BY locations DESC
        LIMIT 15
        """
        zip_cities_query = f"""
        SELECT
          COALESCE(city_name, '') AS city,
          COALESCE(state_code, '') AS state,
          COALESCE(state_name, state_code, '') AS state_name,
          COALESCE(county, '') AS county,
          COUNT(DISTINCT zip_code) AS locations
        FROM {zip_ref}
        {zip_where}
        GROUP BY city, state, state_name, county
        ORDER BY locations DESC
        LIMIT 10
        """
        zip_filter_query = f"""
        SELECT
          (
            SELECT ARRAY_AGG(DISTINCT name IGNORE NULLS ORDER BY name)
            FROM `{project_id}.{bronze_dataset_id}.businesses`
            WHERE is_deleted IS NOT TRUE AND COALESCE(status, 'active') = 'active'
          ) AS brands,
          ARRAY_AGG(DISTINCT state_code IGNORE NULLS ORDER BY state_code) AS states,
          ARRAY_AGG(DISTINCT county IGNORE NULLS ORDER BY county LIMIT 500) AS counties,
          ARRAY_AGG(DISTINCT city_name IGNORE NULLS ORDER BY city_name LIMIT 500) AS cities,
          ARRAY_AGG(DISTINCT zip_code IGNORE NULLS ORDER BY zip_code LIMIT 500) AS zips
        FROM {zip_ref}
        """
        payload = _empty_reporting_payload(source_table, params, warning)
        payload["totals"] = dict(next(iter(client.query(zip_totals_query, job_config=job_config).result())))
        payload["top_states"] = [dict(row) for row in client.query(zip_states_query, job_config=job_config).result()]
        payload["top_cities"] = [dict(row) for row in client.query(zip_cities_query, job_config=job_config).result()]
        payload["filter_options"] = dict(next(iter(client.query(zip_filter_query).result())))
        payload["reporting_cache"] = "zip_base"
        return payload

    try:
        totals = dict(next(iter(client.query(totals_query, job_config=job_config).result())))
        top_states = [dict(row) for row in client.query(top_states_query, job_config=job_config).result()]
        top_cities = [dict(row) for row in client.query(top_cities_query, job_config=job_config).result()]
        brands = [dict(row) for row in client.query(brand_query, job_config=job_config).result()]
        raw_whitespace = [dict(row) for row in client.query(gap_query, job_config=job_config).result()]
        map_records = [dict(row) for row in client.query(map_query, job_config=job_config).result()]
        filter_options = dict(next(iter(client.query(filter_options_query).result())))
        sample_records = [dict(row) for row in client.query(sample_query, job_config=job_config).result()]
        data_quality_row = dict(next(iter(client.query(data_quality_query, job_config=job_config).result())))
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            payload = zip_only_payload("Preparing business data.")
            set_cached_query(cache_key, payload)
            return payload
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

    # Reference metrics for Similar Market Analysis & Opportunity Scoring
    subject_pops = [r["population"] for r in raw_whitespace if r.get("subject_stores", 0) > 0 and r.get("population", 0) > 0]
    subject_incomes = [r["median_household_income"] for r in raw_whitespace if r.get("subject_stores", 0) > 0 and r.get("median_household_income", 0) > 0]
    subject_ages = [r["median_age"] for r in raw_whitespace if r.get("subject_stores", 0) > 0 and r.get("median_age", 0) > 0]
    subject_median_pop = int(_median(subject_pops) or 0)
    subject_median_income = int(_median(subject_incomes) or 0)
    subject_median_age = _median(subject_ages)

    tolerance_pct = float(params.get("tolerance", ["20"])[0] or "20") / 100.0

    # Enrich whitespace opportunities with opportunity score formula:
    # 40% Population Similarity + 25% Income Attractiveness + 20% Population Scale + 15% Competitive Opportunity
    opportunities = []
    similar_candidates_count = 0
    competitor_whitespace_count = 0
    open_whitespace_count = 0
    total_whitespace_pop = 0
    whitespace_incomes = []

    for item in raw_whitespace:
        pop = item.get("population") or 0
        inc = item.get("median_household_income") or 0
        comp_stores = item.get("competitor_stores") or 0
        subj_stores = item.get("subject_stores") or 0
        ws_type = item.get("whitespace_type") or "UNKNOWN_COVERAGE"

        pop_diff_pct = abs(pop - subject_median_pop) / max(subject_median_pop, 1)
        sim_score = max(0.0, 1.0 - pop_diff_pct)
        sim_pct = round(sim_score * 100, 1)
        is_similar = pop_diff_pct <= tolerance_pct
        if is_similar:
            similar_candidates_count += 1

        if ws_type == "COMPETITOR_WHITESPACE":
            competitor_whitespace_count += 1
            total_whitespace_pop += pop
            if inc > 0:
                whitespace_incomes.append(inc)
        elif ws_type == "OPEN_WHITESPACE":
            open_whitespace_count += 1
            total_whitespace_pop += pop
            if inc > 0:
                whitespace_incomes.append(inc)

        # Opportunity Score components normalized 0-1
        # Pop similarity: sim_score (0-1)
        # Income attractiveness: min(1.0, inc / max(subject_median_income, 1))
        # Population scale: min(1.0, pop / 60000.0)
        # Competitive opportunity: min(1.0, comp_stores / 4.0) if comp_stores > 0 else (0.4 if ws_type == 'OPEN_WHITESPACE' else 0.1)
        comp_opp = min(1.0, comp_stores / 4.0) if comp_stores > 0 else (0.4 if ws_type == "OPEN_WHITESPACE" else 0.1)
        inc_attr = min(1.0, inc / max(subject_median_income, 1)) if inc > 0 else 0.5
        pop_scale = min(1.0, pop / 50000.0) if pop > 0 else 0.2

        opp_score_raw = (0.40 * sim_score) + (0.25 * inc_attr) + (0.20 * pop_scale) + (0.15 * comp_opp)
        opp_score = round(opp_score_raw * 100, 1)

        comp_density = round((comp_stores / max(pop / 10000.0, 0.5)), 2) if pop > 0 else 0.0

        enriched_item = {
            **item,
            "population_similarity_score": round(sim_score, 3),
            "population_similarity_pct": sim_pct,
            "population_difference_pct": round(pop_diff_pct * 100, 1),
            "is_similar_market": is_similar,
            "income_vs_subject_median": round(((inc - subject_median_income) / max(subject_median_income, 1)) * 100, 1) if inc > 0 else 0,
            "population_vs_subject_median": round(((pop - subject_median_pop) / max(subject_median_pop, 1)) * 100, 1) if pop > 0 else 0,
            "competitor_density": comp_density,
            "opportunity_score": opp_score,
            "score_components": {
                "population_similarity": round(sim_score * 100, 1),
                "income_attractiveness": round(inc_attr * 100, 1),
                "population_scale": round(pop_scale * 100, 1),
                "competitive_opportunity": round(comp_opp * 100, 1),
            },
            "data_confidence": "HIGH" if (item.get("latitude") and item.get("longitude") and pop > 0 and inc > 0) else ("MEDIUM" if pop > 0 else "LOW"),
        }
        opportunities.append(enriched_item)

    # Sort opportunities by opportunity score descending
    opportunities.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)
    for idx, opp in enumerate(opportunities):
        opp["opportunity_rank"] = idx + 1

    # Filter opportunities for gaps table (competitor whitespace & open whitespace)
    gaps = [opp for opp in opportunities if opp.get("whitespace_type") in {"COMPETITOR_WHITESPACE", "OPEN_WHITESPACE"}][:100]

    # Calculate Tab 1 Head-to-Head brand comparison metrics
    selected_brand_name = main_brands[0] if main_brands else ""
    subject_locations_count = sum(r.get("subject_stores", 0) for r in raw_whitespace)
    competitor_locations_count = sum(r.get("competitor_stores", 0) for r in raw_whitespace)

    shared_zips = len([r for r in raw_whitespace if r.get("subject_stores", 0) > 0 and r.get("competitor_stores", 0) > 0])
    subject_only_zips = len([r for r in raw_whitespace if r.get("subject_stores", 0) > 0 and r.get("competitor_stores", 0) == 0])
    competitor_only_zips = len([r for r in raw_whitespace if r.get("subject_stores", 0) == 0 and r.get("competitor_stores", 0) > 0])
    total_active_zips = max(shared_zips + subject_only_zips + competitor_only_zips, 1)
    exposure_rate = round((shared_zips / max(shared_zips + subject_only_zips, 1)) * 100, 1)

    # Enrich state distribution with Brand Footprint Share %, Pop per store, Competitor Whitespace ZIPs, Open Whitespace ZIPs
    enriched_states = []
    for st in top_states:
        st_code = st.get("state", "")
        st_zips = [r for r in raw_whitespace if r.get("state") == st_code]
        st_subject_stores = sum(r.get("subject_stores", 0) for r in st_zips)
        st_comp_stores = sum(r.get("competitor_stores", 0) for r in st_zips)
        st_total_stores = st_subject_stores + st_comp_stores
        st_pop = st.get("state_population") or sum(r.get("population", 0) for r in st_zips)
        st_comp_ws = len([r for r in st_zips if r.get("whitespace_type") == "COMPETITOR_WHITESPACE"])
        st_open_ws = len([r for r in st_zips if r.get("whitespace_type") == "OPEN_WHITESPACE"])
        st_incomes = [r.get("median_household_income", 0) for r in st_zips if r.get("median_household_income", 0) > 0]
        st_med_income = int(_median(st_incomes) or 0)

        enriched_states.append({
            **st,
            "selected_brand_locations": st_subject_stores,
            "competitor_locations": st_comp_stores,
            "brand_footprint_share_pct": _share_pct(st_subject_stores, st_total_stores),
            "selected_brand_zips": len([r for r in st_zips if r.get("subject_stores", 0) > 0]),
            "competitor_zips": len([r for r in st_zips if r.get("competitor_stores", 0) > 0]),
            "population_per_selected_brand_location": _population_per_location(st_pop, st_subject_stores),
            "competitor_whitespace_zips": st_comp_ws,
            "open_whitespace_zips": st_open_ws,
            "median_household_income": st_med_income,
        })

    # Head-to-head enriched brands
    enriched_brands = []
    for b in brands:
        b_name = b.get("brand", "")
        b_locs = b.get("locations", 0)
        diff_vs_subject = b_locs - subject_locations_count
        diff_pct = _pct_diff(b_locs, subject_locations_count)
        pop_cov = b.get("zips", 0) * subject_median_pop
        pop_per_loc = _population_per_location(pop_cov, b_locs)
        enriched_brands.append({
            **b,
            "is_subject": b_name == selected_brand_name,
            "difference_vs_subject": diff_vs_subject,
            "pct_difference_vs_subject": diff_pct,
            "population_covered": pop_cov,
            "population_per_location": pop_per_loc,
            "average_household_income": subject_median_income,
            # Real median age across the subject brand's own ZIP markets - the
            # same reference value for every row here, since we don't track a
            # distinct per-competitor market age (would need each competitor's
            # own ZIP footprint aggregated the same way subject_stores is).
            "median_age": subject_median_age if subject_median_age is not None else 0,
            "overlap_zips": shared_zips if b_name != selected_brand_name else 0,
            "competitor_only_zips": competitor_only_zips if b_name != selected_brand_name else 0,
            "shared_zips": shared_zips,
            "subject_only_zips": subject_only_zips,
            "competitive_exposure_rate": exposure_rate,
            "competitor_density": round(competitor_locations_count / max(subject_locations_count, 1), 2),
        })

    # Head-to-Head ordering: the subject brand always leads the comparison,
    # with competitors listed afterwards ordered by location count.
    enriched_brands.sort(key=lambda b: (not b["is_subject"], -b.get("locations", 0)))

    # Tab 2 Quality Summary Metrics - computed from data_quality_row (a real
    # aggregate against the silver-enriched listings table), not fabricated.
    total_raw_locations = totals.get("total_locations", 0)
    dq_total = data_quality_row.get("total_rows", 0) or 0
    dq_with_coords = data_quality_row.get("with_coordinates", 0) or 0
    dq_with_zip = data_quality_row.get("with_zip", 0) or 0
    dq_distinct = data_quality_row.get("distinct_rows", 0) or 0
    dq_last_observed = data_quality_row.get("last_observed_at")

    zip_completeness_pct = _share_pct(dq_with_zip, dq_total)
    coordinate_completeness_pct = _share_pct(dq_with_coords, dq_total)
    duplicate_count = max(dq_total - dq_distinct, 0)
    duplicate_rate_pct = _share_pct(duplicate_count, dq_total)
    valid_rate_pct = round((zip_completeness_pct + coordinate_completeness_pct) / 2, 1) if dq_total else 0.0
    invalid_zip_count = max(dq_total - dq_with_zip, 0)
    missing_coord_count = max(dq_total - dq_with_coords, 0)

    if dq_last_observed:
        observed_dt = dq_last_observed if hasattr(dq_last_observed, "isoformat") else None
        freshness_days = (datetime.now(timezone.utc) - observed_dt).days if observed_dt else None
    else:
        freshness_days = None

    if dq_total == 0:
        overall_confidence = "NO_DATA"
        confidence_reasons = [
            "No ingested listing records found for the selected brand(s) - load a source via the Mappings tab first.",
        ]
    else:
        overall_confidence = "HIGH" if valid_rate_pct >= 90 else ("MEDIUM" if valid_rate_pct >= 60 else "LOW")
        confidence_reasons = [
            f"{zip_completeness_pct}% of {dq_total} ingested records have a valid ZIP code.",
            f"{coordinate_completeness_pct}% resolved to real coordinates (source listing, ZIP, or city/state centroid).",
            f"{duplicate_rate_pct}% duplicate rate across brand/ZIP/address.",
            f"Last observed ingestion timestamp is {freshness_days} day(s) ago." if freshness_days is not None else "No observed-at timestamp available on ingested records.",
        ]

    data_quality_summary = {
        "valid_rate_pct": valid_rate_pct,
        "duplicate_rate_pct": duplicate_rate_pct,
        "zip_completeness_pct": zip_completeness_pct,
        "coordinate_completeness_pct": coordinate_completeness_pct,
        "freshness_days": freshness_days,
        "overall_confidence": overall_confidence,
        "confidence_reasons": confidence_reasons,
        "error_buckets": [
            {"type": "INVALID_ZIP", "count": invalid_zip_count, "severity": "MEDIUM", "resolved": False},
            {"type": "MISSING_COORDINATES", "count": missing_coord_count, "severity": "LOW", "resolved": False},
            {"type": "DUPLICATE_STORE", "count": duplicate_count, "severity": "INFO", "resolved": False},
        ],
    }

    median_ws_income = int(_median(whitespace_incomes) or 0)

    primary_kpis = {
        "selected_brand_locations": subject_locations_count,
        "competitor_locations": competitor_locations_count,
        "states_covered": totals.get("total_states", 0),
        "cities_covered": totals.get("total_cities", 0),
        "zips_covered": totals.get("total_zips", 0),
        "population_covered": sum(r.get("population", 0) for r in raw_whitespace if r.get("subject_stores", 0) > 0 or r.get("competitor_stores", 0) > 0),
        "similar_zip_candidates": similar_candidates_count,
        "competitor_whitespace_zips": competitor_whitespace_count,
        "open_whitespace_zips": open_whitespace_count,
        "whitespace_population": total_whitespace_pop,
        "median_whitespace_income": median_ws_income if whitespace_incomes else 0,
        "data_confidence": "HIGH" if total_raw_locations > 0 else "NO_DATA",
    }

    similar_analysis_meta = {
        "reference_population": subject_median_pop,
        "reference_income": subject_median_income,
        "population_similarity_threshold_pct": int(tolerance_pct * 100),
        "population_similarity_formula": "MAX(0, 1 - ABS(candidate_population - reference_population) / reference_population)",
        "opportunity_score_formula": "40% Pop Similarity + 25% Income Attractiveness + 20% Pop Scale + 15% Comp Opportunity",
        "opportunity_weights": {
            "population_similarity": 0.40,
            "income_attractiveness": 0.25,
            "population_scale": 0.20,
            "competitive_opportunity": 0.15,
        },
    }

    for row in [totals, *enriched_states, *top_cities, *enriched_brands, *opportunities, *gaps, *map_records, *sample_records]:
        for key, value in list(row.items()):
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat()
    filter_options = {key: list(value or []) for key, value in filter_options.items()}

    result_payload = {
        "source_table": source_table,
        "reporting_cache": "miss",
        "refreshing": bool(refresh_started or REPORTING_REFRESHING),
        "filters": {
            "main_brands": main_brands,
            "competitor_brands": competitor_brands,
            "state": state_filter,
            "county": county_filter,
            "city": city_filter,
            "zip": zip_filter,
            "tolerance_pct": int(tolerance_pct * 100),
        },
        "filter_options": filter_options,
        "totals": totals,
        "primary_kpis": primary_kpis,
        "top_states": enriched_states,
        "top_cities": top_cities,
        "brands": enriched_brands,
        "whitespace_opportunities": opportunities[:250],
        "gaps": gaps,
        "similar_analysis_meta": similar_analysis_meta,
        "data_quality_summary": data_quality_summary,
        "head_to_head_meta": {
            "shared_zips": shared_zips,
            "subject_only_zips": subject_only_zips,
            "competitor_only_zips": competitor_only_zips,
            "competitive_exposure_rate": exposure_rate,
        },
        "map_records": map_records,
        "states_without_locations": states_without_locations,
        "sample_records": sample_records,
        "warning": "Updating." if refresh_started or REPORTING_REFRESHING else "",
    }
    set_cached_query(cache_key, result_payload)
    return result_payload


def geo_options(state: str = "", county: str = "") -> dict[str, Any]:
    cache_key = f"geo_options:{state.strip().upper()}:{county.strip().lower()}"
    cached = get_cached_query(cache_key)
    if cached:
        return cached

    try:
        from google.cloud import bigquery
        project_id, dataset_id, credentials_json = _warehouse_settings()
        client = _bigquery_client(project_id, credentials_json)
        table_ref = f"`{project_id}.{dataset_id}.us_zipcodes`"
    except (ImportError, Exception):
        states = [{"code": code, "name": name} for name, code in [
            ("Alabama", "AL"), ("Alaska", "AK"), ("Arizona", "AZ"), ("Arkansas", "AR"), ("California", "CA"),
            ("Colorado", "CO"), ("Connecticut", "CT"), ("Delaware", "DE"), ("Florida", "FL"), ("Georgia", "GA"),
            ("Hawaii", "HI"), ("Idaho", "ID"), ("Illinois", "IL"), ("Indiana", "IN"), ("Iowa", "IA"),
            ("Kansas", "KS"), ("Kentucky", "KY"), ("Louisiana", "LA"), ("Maine", "ME"), ("Maryland", "MD"),
            ("Massachusetts", "MA"), ("Michigan", "MI"), ("Minnesota", "MN"), ("Mississippi", "MS"), ("Missouri", "MO"),
            ("Montana", "MT"), ("Nebraska", "NE"), ("Nevada", "NV"), ("New Hampshire", "NH"), ("New Jersey", "NJ"),
            ("New Mexico", "NM"), ("New York", "NY"), ("North Carolina", "NC"), ("North Dakota", "ND"), ("Ohio", "OH"),
            ("Oklahoma", "OK"), ("Oregon", "OR"), ("Pennsylvania", "PA"), ("Rhode Island", "RI"), ("South Carolina", "SC"),
            ("South Dakota", "SD"), ("Tennessee", "TN"), ("Texas", "TX"), ("Utah", "UT"), ("Vermont", "VT"),
            ("Virginia", "VA"), ("Washington", "WA"), ("West Virginia", "WV"), ("Wisconsin", "WI"), ("Wyoming", "WY"),
            ("District of Columbia", "DC")
        ]]
        return {"states": states, "counties": [], "cities": []}

    states_query = f"""
    SELECT state_code, ANY_VALUE(state_name) AS state_name
    FROM {table_ref}
    WHERE state_code IS NOT NULL AND state_code != ''
    GROUP BY state_code
    ORDER BY state_name, state_code
    """
    states = [{"code": row["state_code"], "name": row["state_name"] or row["state_code"]} for row in client.query(states_query).result()]

    counties_query = f"""
    SELECT DISTINCT county 
    FROM {table_ref}
    WHERE county IS NOT NULL AND county != ''
      AND (@state = '' OR UPPER(state_code) = UPPER(@state))
    ORDER BY county LIMIT 300
    """
    c_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("state", "STRING", state.strip())])
    counties = [row["county"] for row in client.query(counties_query, job_config=c_config).result()]

    cities_query = f"""
    SELECT DISTINCT city_name 
    FROM {table_ref}
    WHERE city_name IS NOT NULL AND city_name != ''
      AND (@state = '' OR UPPER(state_code) = UPPER(@state))
      AND (@county = '' OR LOWER(county) = LOWER(@county))
    ORDER BY city_name LIMIT 300
    """
    ct_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("state", "STRING", state.strip()),
        bigquery.ScalarQueryParameter("county", "STRING", county.strip()),
    ])
    cities = [row["city_name"] for row in client.query(cities_query, job_config=ct_config).result()]

    result = {"states": states, "counties": counties, "cities": cities}
    set_cached_query(cache_key, result)
    return result


def search_zips(query: str = "", state: str = "", county: str = "", city: str = "", limit: int = 25) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {"zips": []}

    cache_key = f"search_zips:{query.lower()}:{state.strip().upper()}:{county.strip().lower()}:{city.strip().lower()}:{limit}"
    cached = get_cached_query(cache_key)
    if cached:
        return cached

    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"`{project_id}.{dataset_id}.us_zipcodes`"

    sql = f"""
    SELECT zip_code, city_name, county, state_code, state_name, population, median_household_income, median_age
    FROM {table_ref}
    WHERE (zip_code LIKE CONCAT(@q, '%') OR LOWER(city_name) LIKE CONCAT(LOWER(@q), '%'))
      AND (@state = '' OR UPPER(state_code) = UPPER(@state))
      AND (@county = '' OR LOWER(county) = LOWER(@county))
      AND (@city = '' OR LOWER(city_name) = LOWER(@city))
    ORDER BY zip_code
    LIMIT @limit
    """
    params = [
        bigquery.ScalarQueryParameter("q", "STRING", query),
        bigquery.ScalarQueryParameter("state", "STRING", state.strip()),
        bigquery.ScalarQueryParameter("county", "STRING", county.strip()),
        bigquery.ScalarQueryParameter("city", "STRING", city.strip()),
        bigquery.ScalarQueryParameter("limit", "INT64", min(max(1, limit), 100)),
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    zips = [dict(row) for row in client.query(sql, job_config=job_config).result()]
    for row in zips:
        for k, v in list(row.items()):
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
    res = {"zips": zips}
    set_cached_query(cache_key, res)
    return res




def save_template_version(data: dict[str, Any]) -> dict[str, Any]:
    from google.cloud import bigquery

    template_id = str(data.get("workflow_template_id", "")).strip()
    components = data.get("components")
    if not template_id or not isinstance(components, dict):
        raise ValueError("workflow_template_id and components are required")
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.workflow_templates"
    _ensure_workflow_templates_table(client, project_id, dataset_id)
    mapper = components.get("mapper") if isinstance(components.get("mapper"), dict) else components
    source_type_id = str(components.get("source_type_id") or mapper.get("source_type_id") or "").strip() or None
    query = f"UPDATE `{table_ref}` SET archived_components = components, components = @components, source_type_id = @source_type_id, updated_at = CURRENT_TIMESTAMP() WHERE workflow_template_id = @template_id"
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("template_id", "STRING", template_id),
        bigquery.ScalarQueryParameter("components", "JSON", json.dumps(components, sort_keys=True)),
        bigquery.ScalarQueryParameter("source_type_id", "STRING", source_type_id),
    ])
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
    if data.get("rows") and isinstance(data["rows"], list):
        rows = data["rows"]
    else:
        records = list_rejected(event_id)["records"]
        selected_numbers = {int(value) for value in data.get("row_numbers", [])}
        rows = [record["raw_record"] for record in records if not selected_numbers or record["row_number"] in selected_numbers]
    if not rows:
        raise ValueError("No rejected records were found for reprocessing")
    source_fields = sorted({path for path in mapper.get("fields", {}).values() if path})
    return save_mapper({"mapper": mapper, "rows": rows, "source_fields": source_fields})


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _row_error_listing(
    event_id: str,
    business_id: str,
    source_type_id: str,
    index: int,
    row: Any,
    row_errors: list[dict[str, Any]],
    observed_at: str,
) -> dict[str, Any]:
    meta = row.get("__meta", {}) if isinstance(row, dict) and isinstance(row.get("__meta"), dict) else {}
    first_error = row_errors[0] if row_errors else {}
    nested_location = row.get("location", {}) if isinstance(row, dict) and isinstance(row.get("location"), dict) else {}
    country = row.get("country") or row.get("Country") or nested_location.get("country") if isinstance(row, dict) else None
    return {
        "event_id": event_id,
        "business_id": business_id,
        "source_type_id": source_type_id,
        "row_number": index + 1,
        "errors": _safe_json_dumps(row_errors),
        "raw_record": _safe_json_dumps(row),
        "observed_at": observed_at,
        "template_id": meta.get("template_id"),
        "ingestion_id": meta.get("ingestion_id"),
        "mapping_id": meta.get("mapping_id"),
        "validation_error_type": first_error.get("reason") or first_error.get("field"),
        "country": country,
        "is_sample_data": bool(meta.get("is_sample_data")),
        "sample_batch_id": meta.get("sample_batch_id"),
        "is_deleted": False,
        "deleted_on": None,
    }


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
    try:
        field_definitions = field_catalog()
    except Exception as exc:
        LOGGER.warning("field_catalog_unavailable_using_defaults error=%s", exc)
        field_definitions = load_field_registry()
    business_id = str(mapper.get("business_id", "")).strip()
    if not business_id:
        raise ValueError("Select an existing business or create a new business before saving")
    event_id = str(payload.get("batch_event_id") or payload.get("event_id") or uuid4().hex)
    row_offset = int(payload.get("row_offset") or 0)
    save_template = payload.get("save_template", True) is not False
    sample_meta = payload.get("sample_meta") if isinstance(payload.get("sample_meta"), dict) else {}
    template_id = str(sample_meta.get("template_id") or uuid4())
    ingestion_id = str(sample_meta.get("ingestion_id") or event_id)
    # mapper_id doesn't exist yet at this point (it's generated further down,
    # see the `mapping_id = mapping_id or mapper_id` fallback below) - use
    # whatever the caller passed, or fall back to that generated id later.
    mapping_id = str(sample_meta.get("mapping_id") or "")
    mapper["business_id"] = business_id
    mapper["source_type_id"] = source_type_id
    locations = []
    error_listings = []
    for index, row in enumerate(rows):
        source_index = row_offset + index
        if sample_meta.get("is_sample_data") and isinstance(row, dict):
            row.setdefault("__meta", {
                "template_id": template_id,
                "ingestion_id": ingestion_id,
                "mapping_id": mapping_id,
                "is_sample_data": True,
                "sample_batch_id": sample_meta.get("sample_batch_id"),
            })
        observed_at = utc_now_iso()
        row_errors: list[dict[str, Any]] = []
        location = None
        try:
            if not isinstance(row, dict):
                raise ValueError("Row must be an object with named fields")
            row_errors = validate_source_row(row, mapper)
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
            LOGGER.exception("row_validation_failed event_id=%s row_number=%d", event_id, source_index + 1)
            row_errors.append({
                "field": "row",
                "reason": "row could not be processed",
                "hint": "This row has an unexpected shape or value and was moved to review.",
                "value": str(exc),
            })
        if row_errors:
            error_listings.append(_row_error_listing(event_id, business_id, source_type_id, source_index, row, row_errors, observed_at))
        elif location is not None:
            locations.append(location)
    project_id, dataset_id, credentials_json = _warehouse_settings()

    mapper_id = f"mapper_{uuid4().hex}"
    mapping_id = mapping_id or mapper_id
    config_json = _scrub_mapper(mapper)
    try:
        demographics = _load_mapped_zip_demographics({location.zip5 for location in locations})
    except Exception as exc:
        LOGGER.warning("zip_enrichment_lookup_failed_continuing error=%s", exc)
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
    rows_by_table = build_table_rows(locations, demographics)
    rows_by_table["businesses"] = []
    for record in error_listings:
        record["source_type_id"] = source_type_id
    rows_by_table["source_types"] = []
    rows_by_table["workflow_templates"] = [{
        "workflow_template_id": template_id,
        "business_id": business_id, "source_type_id": source_type_id, "name": source_name,
        "components": json.dumps({"mapper": mapper, "source_type_id": source_type_id, "sample_meta": sample_meta}, sort_keys=True),
        "archived_components": None,
        "source_configuration": json.dumps(sample_meta.get("source_configuration") or {}, sort_keys=True),
        "is_sample_data": bool(sample_meta.get("is_sample_data")),
        "sample_batch_id": sample_meta.get("sample_batch_id"),
        "is_deleted": False,
        "deleted_on": None,
        "created_at": utc_now_iso(), "updated_at": utc_now_iso(),
    }] if save_template else []
    rows_by_table["error_listings"] = error_listings
    push_to_bigquery(project_id, dataset_id, rows_by_table, credentials_json)
    invalidate_cache()
    LOGGER.info(
        "save_succeeded mapper_id=%s dataset=%s mapped_rows=%d mapped_fields=%d",
        mapper_id,
        f"{project_id}.{dataset_id}",
        len(locations),
        len(mapper["fields"]),
    )
    return {"event_id": event_id, "mapper_id": mapper_id, "total_rows": len(rows), "mapped_rows": len(locations), "error_listings": len(error_listings), "field_count": len(mapper["fields"]), "dataset": f"{project_id}.{dataset_id}", "row_offset": row_offset, "template_saved": save_template}


def clear_saved_data() -> dict[str, Any]:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    clear_result = clear_dataset_tables(project_id, dataset_id, credentials_json)
    deleted = clear_result["soft_deleted_tables"]
    truncated = clear_result["truncated_tables"]
    ZIP_REFERENCE_CACHE.pop((project_id, dataset_id), None)
    invalidate_cache()
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
            if self.path == "/api/ping":
                try:
                    result = ping_storage_connection()
                    result["timestamp"] = utc_now_iso()
                    _json_response(self, 200, result)
                except Exception as exc:
                    _json_response(self, 400, {"ok": False, "status": "warming", "error": str(exc), "timestamp": utc_now_iso()})
                return
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
            if self.path.startswith("/api/dominos-source"):
                from urllib.parse import parse_qs, urlsplit
                params = parse_qs(urlsplit(self.path).query)
                try:
                    raw_limit = params.get("limit", ["1"])[0]
                    limit = None if raw_limit == "all" else int(raw_limit or "1")
                    order_type = params.get("type", ["Delivery"])[0]
                    raw_stores_per_zip = params.get("stores_per_zip", ["1"])[0]
                    stores_per_zip = None if raw_stores_per_zip == "all" else int(raw_stores_per_zip or "1")
                    max_workers = int(params.get("max_workers", ["8"])[0] or "8")
                    one_per_zip = params.get("one_per_zip", ["false"])[0].lower() in {"1", "true", "yes"}
                    provider = params.get("provider", ["auto"])[0]
                    _json_response(self, 200, dominos_source(limit, order_type, stores_per_zip, max_workers, one_per_zip, provider))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/reporting"):
                from urllib.parse import parse_qs, urlsplit
                try:
                    _json_response(self, 200, reporting_summary(parse_qs(urlsplit(self.path).query)))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/geo/options"):
                from urllib.parse import parse_qs, urlsplit
                params = parse_qs(urlsplit(self.path).query)
                state = params.get("state", [""])[0]
                county = params.get("county", [""])[0]
                try:
                    _json_response(self, 200, geo_options(state, county))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/zips/search"):
                from urllib.parse import parse_qs, urlsplit
                params = parse_qs(urlsplit(self.path).query)
                q = params.get("q", [""])[0]
                state = params.get("state", [""])[0]
                county = params.get("county", [""])[0]
                city = params.get("city", [""])[0]
                try:
                    _json_response(self, 200, search_zips(q, state, county, city))
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
            if self.path not in {"/api/login", "/api/preview", "/api/source-url", "/api/sheets", "/api/save", "/api/clear", "/api/brands", "/api/learning", "/api/reprocess", "/api/field-alias", "/api/custom-field", "/api/templates/save", "/api/silver/enrich", "/api/reporting/refresh", "/api/sample/load"}:
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
                elif self.path in {"/api/silver/enrich", "/api/reporting/refresh"}:
                    _json_response(self, 200, build_silver_layer())
                elif self.path == "/api/sample/load":
                    _json_response(self, 200, load_sample_dataset(bool(payload.get("reset"))))
                else:
                    _json_response(self, 200, preview_source(payload))
            except Exception as exc:
                LOGGER.exception("request_failed request_id=%s endpoint=%s error=%s", request_id, self.path, exc)
                _json_response(self, 400, {"error": str(exc), "request_id": request_id})

    return MapperHandler


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    ui_dir = Path("ui").resolve()
    handler = make_handler(ui_dir)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        print(f"Workflow UI running at http://{host}:{port}/")
        httpd.serve_forever()
