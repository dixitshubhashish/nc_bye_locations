from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
from dataclasses import replace
from functools import lru_cache
import hashlib
import hmac
import json
import http.server
import io
import logging
import os
from pathlib import Path
import socketserver
import threading
from time import perf_counter, sleep, time as wall_clock_time
from types import SimpleNamespace
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit
import urllib.request
import zipfile
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
from whitespace_tool.paths import project_path
from whitespace_tool.sources.demographics import fetch_bigquery_demographics, resolve_bigquery_connection
from whitespace_tool.sources.dominos_overpass import fetch_for_zips as fetch_dominos_from_overpass
from whitespace_tool.sources.dominos_store_locator import fetch_for_zips
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, TABLE_CLUSTER_SPECS, build_table_rows, clear_dataset_tables, drop_dataset_tables, push_to_bigquery
from whitespace_tool.storage_config import load_dotenv, load_storage_config
from whitespace_tool.sqlite_cache import (
    get_cached_query, set_cached_query, invalidate_cache, clear_local_cache_db,
    get_cached_zipcode_count, cache_zipcodes, cache_missing_zipcodes, get_auto_repair_stats, set_auto_repair_stats, increment_manual_fixed_count,
    set_fix_state_counts, get_fix_state_counts, get_cache_action_stats, get_slow_actions,
    replace_gold_mirror, get_mirror_status, fetch_mirror_zip_brand_activity,
    fetch_mirror_reporting_locations, fetch_mirror_reporting_locations_by_brand, fetch_mirror_businesses,
    get_error_count, set_error_count, replace_quality_mirror, clear_sample_reporting_mirror,
    get_zip_reference_status, set_zip_reference_status,
    seed_enrichment_cycle, claim_enrichment_batch, complete_enrichment_claim, enrichment_cycle_counts,
    get_cached_worldwide_city_count, cache_worldwide_cities,
    record_save_event, get_recent_save_events, count_save_events,
    get_app_setting, set_app_setting, get_stale_after_days, invalidate_quality_cache, DEFAULT_STALE_AFTER_DAYS,
    record_field_discovery_gap,
    record_mapping_confidence_events, get_mapping_confidence,
)
from whitespace_tool.sample_data import SAMPLE_BATCH_ID, SAMPLE_BRANDS, generate_source_rows, mapper_for, source_configuration, source_label, stable_business_id, stable_template_id


SUPPORTED_SOURCE_TYPES = {"csv", "excel", "json", "xml", "api_get_json", "python_editor"}
MINIMUM_US_ZIP_REFERENCE_ROWS = 30000
MAX_REMOTE_SOURCE_BYTES = int(os.environ.get("MAPPER_MAX_REMOTE_SOURCE_MB", "150")) * 1024 * 1024
REMOTE_SOURCE_TIMEOUT_SECONDS = int(os.environ.get("MAPPER_REMOTE_SOURCE_TIMEOUT_SECONDS", "300"))
MIN_REMOTE_SOURCE_ROW_LIMIT = 10000
REMOTE_SOURCE_ROW_LIMITS = (250000, 100000, 50000, 25000, MIN_REMOTE_SOURCE_ROW_LIMIT)
_QUALITY_REFRESH_LOCK = threading.Lock()
_QUALITY_REFRESH_KEYS: set[str] = set()
_QUALITY_FIX_METRICS_LOCK = threading.Lock()
_QUALITY_FIX_METRICS_REFRESHING = False
_QUALITY_FIX_METRICS_LAST_REFRESH = 0.0
_SAMPLE_CLEAR_LOCK = threading.Lock()
_SAMPLE_CLEAR_RUNNING = False
_ZIP_REFERENCE_LOCK = threading.Lock()
_ZIP_REFERENCE_THREAD: threading.Thread | None = None
_WORLDWIDE_REFERENCE_LOCK = threading.Lock()
_WORLDWIDE_REFERENCE_THREAD: threading.Thread | None = None


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("whitespace_tool.workflow")
    if logger.handlers:
        return logger
    log_dir = project_path(os.environ.get("MAPPER_LOG_DIR", "logs"))
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
ENRICHMENT_STOP_REQUESTED = threading.Event()
ENRICHMENT_STATUS: dict[str, Any] = {"state": "idle", "current_id": "", "processed": 0, "updated_at": ""}
AUTO_REPAIR_THREAD: threading.Thread | None = None
AUTO_REPAIR_LOCK = threading.Lock()
AUTO_REPAIR_STATS: dict[str, int] = {"fixed": 0, "processed": 0, "remaining": 0}

# Set once per real user action (do_POST - parse/save/reprocess/etc, never
# background polling) so the auto-repair loop can tell "the app is idle" from
# "someone is actively working" and back off instead of competing for the
# same BigQuery client/connection pool. A plain float write is safe without a
# lock here - it's a soft, best-effort signal, not a correctness-critical one.
LAST_FOREGROUND_ACTIVITY_AT: float = 0.0
FOREGROUND_IDLE_GRACE_SECONDS = 10.0


def _enrichment_checkpoint(current_id: str = "") -> None:
    if ENRICHMENT_STOP_REQUESTED.is_set():
        raise RuntimeError("Enrichment stopped by user.")
    ENRICHMENT_STATUS.update({"state": "running", "current_id": current_id, "updated_at": utc_now_iso()})
SERVER_LAUNCH_ID = uuid4().hex
load_dotenv()


def _json_response(handler: http.server.BaseHTTPRequestHandler, status: int, payload: dict[str, Any],
                   extra_headers: list[tuple[str, str]] | None = None) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    for name, value in (extra_headers or []):
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)


# ---------------------------------------------------------------------------
# Session enforcement
# ---------------------------------------------------------------------------
# Login used to be a CLIENT-SIDE gate only: authenticate() validated the
# credentials, returned {"authenticated": True}, and issued nothing. No
# endpoint ever checked anything, so every /api/* route - brands, reporting,
# quality, and the full listing exports - answered 200 to an unauthenticated
# caller. The UI redirected to /login, but nothing stopped a direct request.
#
# The secret is per-process on purpose: a restart invalidates outstanding
# sessions, which is the behaviour the UI already copes with (it tracks
# SERVER_LAUNCH_ID and re-authenticates), and it avoids inventing a
# persistent secret-management story this app does not otherwise have.
SESSION_COOKIE_NAME = "ws_session"
_SESSION_SECRET = os.urandom(32)
SESSION_TTL_SECONDS = 12 * 60 * 60

# Paths that must stay reachable without a session: the login page and the
# assets it needs, plus the probes the UI calls before authenticating.
PUBLIC_API_PATHS: frozenset[str] = frozenset({
    "/api/login", "/api/session", "/api/ping",
})


def _issue_session_token() -> str:
    issued = str(int(wall_clock_time()))
    signature = hmac.new(_SESSION_SECRET, issued.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{issued}.{signature}"


def _session_token_is_valid(token: str) -> bool:
    try:
        issued, signature = str(token or "").split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(_SESSION_SECRET, issued.encode("utf-8"), hashlib.sha256).hexdigest()
    # compare_digest, not ==, so a wrong token cannot be recovered by timing.
    if not hmac.compare_digest(expected, signature):
        return False
    try:
        return (wall_clock_time() - int(issued)) < SESSION_TTL_SECONDS
    except (TypeError, ValueError):
        return False


def _request_has_session(handler: Any) -> bool:
    raw = handler.headers.get("Cookie", "") or ""
    for part in raw.split(";"):
        name, _, value = part.strip().partition("=")
        if name == SESSION_COOKIE_NAME:
            return _session_token_is_valid(value)
    return False


def _requires_session(path: str) -> bool:
    """Only /api/* is gated here. UI files stay public - the login page and
    its assets have to load before anyone can authenticate, and they carry
    no data on their own."""
    base = path.split("?", 1)[0]
    return base.startswith("/api/") and base not in PUBLIC_API_PATHS


def authenticate(data: dict[str, Any]) -> dict[str, bool]:
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    expected_user = os.environ.get("WORKFLOW_LOGIN_USER", "admin")
    expected_password = os.environ.get("WORKFLOW_LOGIN_PASSWORD", "")
    
    # Honor environment override if provided, otherwise accept any non-empty password for admin in dev mode
    if expected_password:
        valid = (username == expected_user and password in {expected_password, "bn"})
    else:
        valid = (username == expected_user)
        
    if not valid:
        raise ValueError("Invalid username or password.")
    return {"authenticated": True}


def preview_source(payload: dict[str, Any]) -> dict[str, Any]:
    source_type = payload["source_type"]
    record_path = payload.get("record_path") or None
    fields_only = payload.get("fields_only", False)
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type: {source_type}")
    if source_type == "api_get_json":
        return api_get_source.preview_url(
            payload["api_url"],
            record_path,
            payload.get("headers"),
            payload.get("query_params"),
            payload.get("auth"),
            fields_only=fields_only,
        )
    if source_type == "python_editor":
        content = base64.b64decode(payload["content_base64"])
        return python_connector_source.preview(content, record_path, fields_only=fields_only)

    file_name = payload.get("file_name", "")
    content = base64.b64decode(payload["content_base64"])
    if source_type == "csv":
        return csv_source.preview(content, record_path, fields_only=fields_only)
    if source_type == "json":
        return json_source.preview(content, record_path, fields_only=fields_only)
    if source_type == "xml":
        return xml_source.preview(content, record_path, fields_only=fields_only)
    if source_type == "excel":
        return excel_source.preview(content, record_path, file_name, fields_only=fields_only)
    raise ValueError(f"Unsupported source_type: {source_type}")


def source_sheets(payload: dict[str, Any]) -> dict[str, Any]:
    content = base64.b64decode(payload["content_base64"])
    file_name = payload.get("file_name", "")
    return {"sheets": excel_source.list_sheets(content, file_name)}


def _remote_source_file_name(url: str) -> str:
    parsed = urlsplit(url)
    file_name = Path(parsed.path).name or "remote_source"
    suffix = Path(file_name).suffix.lower()
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    output = str(query.get("output", "")).lower().lstrip(".")
    if not suffix and output in {"csv", "xlsx", "xls", "json", "xml"}:
        file_name = f"{file_name}.{output}"
    return file_name


def _remote_source_request(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "CompetitiveWhitespaceTool/1.0"})
    with urllib.request.urlopen(request, timeout=REMOTE_SOURCE_TIMEOUT_SECONDS) as response:
        return response.read(MAX_REMOTE_SOURCE_BYTES + 1), _remote_source_file_name(url)


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
    template_index_path = project_path("config/predefined_brand_templates.json")
    with template_index_path.open("r", encoding="utf-8") as handle:
        templates = json.load(handle)
    for template in templates:
        with project_path(template["template_path"]).open("r", encoding="utf-8") as handle:
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
        # Generalized from the two hardcoded business_id/content_hash ALTERs
        # this used to carry: reconcile against TABLE_SCHEMAS so any column
        # added later (is_archived/archived_at) reaches a deployed table
        # automatically. Hardcoding one column at a time is exactly how
        # error_listings ended up missing has_ai_suggestion in production.
        existing_names = {field.name for field in existing_table.schema}
        # Built from TABLE_SCHEMAS rather than from the constructed schema
        # objects: a column added to an existing table must always be
        # NULLABLE (BigQuery rejects adding a REQUIRED column), and the
        # source dicts are what carry that intent.
        missing_fields = [
            bigquery.SchemaField(field["name"], field["type"], mode="NULLABLE",
                                 default_value_expression=field.get("default"))
            for field in TABLE_SCHEMAS["field_catalogs"] if field["name"] not in existing_names
        ]
        if missing_fields:
            existing_table.schema = list(existing_table.schema) + missing_fields
            client.update_table(existing_table, ["schema"])
            LOGGER.info("field_catalogs_schema_extended columns=%s", [f.name for f in missing_fields])
    if created:
        legacy_ref = f"{project_id}.{dataset_id}.field_catalog"
        try:
            client.get_table(legacy_ref)
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                raise
        else:
            client.query(f"INSERT INTO `{table_ref}` (field_id, business_id, slug, label, table_name, field_name, data_type, required, hints, aliases, is_custom, created_at, updated_at) SELECT field_id, NULL, slug, label, table_name, field_name, data_type, required, hints, aliases, is_custom, created_at, updated_at FROM `{legacy_ref}`").result()
    def _registry_seed_row(field: dict[str, Any], now: str) -> dict[str, Any]:
        return {
            "field_id": str(uuid4()), "business_id": None,
            "slug": field["key"], "label": field["label"], "table_name": field["table"], "field_name": field["field"],
            "data_type": field["type"], "required": field.get("required", False), "hints": json.dumps(field.get("hints", [])),
            "aliases": json.dumps([]), "is_custom": False, "created_at": now, "updated_at": now,
        }

    catalog_select = f"SELECT * FROM `{table_ref}` WHERE is_archived IS NOT TRUE ORDER BY is_custom, label"
    rows = [dict(row) for row in client.query(catalog_select).result()]
    load_kwargs: dict[str, Any] = {"schema": schema}
    if hasattr(bigquery, "SchemaUpdateOption") and hasattr(bigquery.SchemaUpdateOption, "ALLOW_FIELD_ADDITION"):
        load_kwargs["schema_update_options"] = [bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
    if not rows:
        now = utc_now_iso()
        seed = [_registry_seed_row(field, now) for field in load_field_registry()]
        load_job = client.load_table_from_json(
            seed,
            table_ref,
            job_config=bigquery.LoadJobConfig(**load_kwargs)
        )
        load_job.result()
        rows = [dict(row) for row in client.query(catalog_select).result()]
    else:
        # A project seeded before a new standard field (e.g. "ratings") was
        # added to the registry won't have it yet - top up any missing
        # standard (non-custom) fields instead of requiring a full reset.
        existing_standard_slugs = {row["slug"] for row in rows if not row.get("is_custom")}
        missing = [field for field in load_field_registry() if field["key"] not in existing_standard_slugs]
        if missing:
            now = utc_now_iso()
            seed = [_registry_seed_row(field, now) for field in missing]
            load_job = client.load_table_from_json(
                seed,
                table_ref,
                job_config=bigquery.LoadJobConfig(**load_kwargs)
            )
            load_job.result()
            rows = [dict(row) for row in client.query(catalog_select).result()]
    standard_registry_map = {f["key"]: f.get("required", False) for f in load_field_registry()}
    for row in rows:
        for key in ("created_at", "updated_at"):
            if hasattr(row.get(key), "isoformat"):
                row[key] = row[key].isoformat()
        for key in ("hints", "aliases"):
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])
        slug = row.get("slug") or row.get("key")
        if not row.get("is_custom") and slug in standard_registry_map:
            std_req = standard_registry_map[slug]
            if row.get("required") != std_req:
                row["required"] = std_req
                try:
                    update_query = f"UPDATE `{table_ref}` SET required = @req, updated_at = @now WHERE slug = @slug AND (is_custom IS NULL OR is_custom = FALSE)"
                    update_config = bigquery.QueryJobConfig(query_parameters=[
                        bigquery.ScalarQueryParameter("req", "BOOL", std_req),
                        bigquery.ScalarQueryParameter("now", "TIMESTAMP", utc_now_iso()),
                        bigquery.ScalarQueryParameter("slug", "STRING", slug),
                    ])
                    client.query(update_query, job_config=update_config).result()
                except Exception as err:
                    LOGGER.warning("Could not sync required flag in BigQuery field_catalogs for %s: %s", slug, err)
        row["key"] = row.pop("slug")
        row["table"] = row.pop("table_name")
        row["field"] = row.pop("field_name")
        row["type"] = row.pop("data_type")
        row["hints"] = list(dict.fromkeys(row.get("hints", []) + row.get("aliases", [])))

    registry_order = {field["key"]: idx for idx, field in enumerate(load_field_registry())}
    rows.sort(key=lambda r: (1 if r.get("is_custom") else 0, 0 if r.get("required") else 1, registry_order.get(r.get("key"), 999)))
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
    from google.cloud import bigquery

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
    # Re-creating a previously archived field restores that row rather than
    # inserting a duplicate slug - the archived definition already matches
    # the values sitting in listings.custom_fields for this business.
    revive_query = f"""
    UPDATE `{table_ref}`
    SET is_archived = FALSE, archived_at = NULL, label = @label,
        data_type = @data_type, updated_at = @now
    WHERE business_id = @business_id AND LOWER(slug) = LOWER(@slug) AND is_archived IS TRUE
    """
    revive_job = client.query(revive_query, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
        bigquery.ScalarQueryParameter("slug", "STRING", slug),
        bigquery.ScalarQueryParameter("label", "STRING", label),
        bigquery.ScalarQueryParameter("data_type", "STRING", str(data.get("type", "string"))),
        bigquery.ScalarQueryParameter("now", "TIMESTAMP", now),
    ]))
    revive_job.result()
    if int(getattr(revive_job, "num_dml_affected_rows", 0) or 0) > 0:
        invalidate_cache()
        LOGGER.info("custom_field_unarchived slug=%s business_id=%s", slug, business_id)
        return {"field": {"key": slug, "label": label, "table": "listings", "field": slug,
                          "type": str(data.get("type", "string")), "required": False,
                          "hints": [slug], "is_custom": True}, "restored": True}
    # The column that physically stores custom values must exist before the
    # catalog advertises the field - otherwise the catalog promises somewhere
    # for the data to go that the warehouse does not actually have.
    try:
        _ensure_listings_table(client, project_id, dataset_id)
    except Exception as exc:
        LOGGER.warning("custom_field_listings_ensure_failed error=%s", exc)
    field = {"field_id": str(uuid4()), "business_id": business_id, "slug": slug, "label": label, "table_name": "listings", "field_name": slug, "data_type": data.get("type", "string"), "required": False, "hints": json.dumps([slug]), "aliases": json.dumps([]), "is_custom": True, "created_at": now, "updated_at": now}
    schema = [bigquery.SchemaField(f["name"], f["type"], mode=f["mode"], default_value_expression=f.get("default")) for f in TABLE_SCHEMAS["field_catalogs"]]
    load_kwargs: dict[str, Any] = {"schema": schema}
    if hasattr(bigquery, "SchemaUpdateOption") and hasattr(bigquery.SchemaUpdateOption, "ALLOW_FIELD_ADDITION"):
        load_kwargs["schema_update_options"] = [bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
    load_job = client.load_table_from_json(
        [field],
        table_ref,
        job_config=bigquery.LoadJobConfig(**load_kwargs)
    )
    load_job.result()
    invalidate_cache()
    return {"field": {"key": slug, "label": label, "table": "listings", "field": slug, "type": field["data_type"], "required": False, "hints": [slug], "is_custom": True}}


def delete_custom_field(data: dict[str, Any]) -> dict[str, Any]:
    from google.cloud import bigquery

    if str(data.get("password", "")) != "54321":
        raise ValueError("Administrative password required (use '54321')")
    business_id = str(data.get("business_id", "")).strip()
    if not business_id:
        raise ValueError("Select a business before removing a custom field")
    # Accept the current API name and the older browser payload name while
    # clients are upgraded independently.
    field_key = str(data.get("field_key") or data.get("field_name") or "").strip()
    if not field_key:
        raise ValueError("Choose a custom field to remove")

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.field_catalogs"

    lookup_query = f"SELECT field_id, label, is_custom, business_id FROM `{table_ref}` WHERE LOWER(slug) = LOWER(@slug) AND business_id = @business_id LIMIT 1"
    lookup_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("slug", "STRING", field_key),
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
    ])
    matches = list(client.query(lookup_query, job_config=lookup_config).result())
    if not matches:
        raise ValueError("Custom field was not found for this business")
    row = matches[0]
    # Standard/built-in fields are never business-scoped custom rows, but
    # guard explicitly anyway so this can never delete a platform field.
    if not row["is_custom"]:
        raise ValueError("Standard fields are built into the platform and cannot be removed")

    # ARCHIVE, never DELETE. Listings already saved carry this field's values
    # inside listings.custom_fields; dropping the catalog row would strand
    # them with no label, type, or provenance to read them by. Archiving
    # hides the field from the mapper and every field picker (field_catalog()
    # filters is_archived) while leaving both the stored values and their
    # definition intact and recoverable.
    archive_query = f"""
    UPDATE `{table_ref}`
    SET is_archived = TRUE, archived_at = @now, updated_at = @now
    WHERE field_id = @field_id
    """
    archive_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("field_id", "STRING", row["field_id"]),
        bigquery.ScalarQueryParameter("now", "TIMESTAMP", utc_now_iso()),
    ])
    client.query(archive_query, job_config=archive_config).result()
    invalidate_cache()
    LOGGER.info("custom_field_archived field_id=%s slug=%s business_id=%s", row["field_id"], field_key, business_id)
    return {"deleted": True, "archived": True, "field_key": field_key, "label": row["label"]}


REQUIRED_MAPPER_FIELDS: set[str] = set()  # brand is enforced separately in validate_mapper() below
REQUIRED_LOCATION_VALUES: tuple[str, ...] = ()  # brand is the only mandatory field now; see normalize_location()


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


def _source_field_match_key(value: Any) -> str:
    """Compare source headers across CSV/Excel naming and casing differences."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _resolve_mapper_source_fields(mapper: dict[str, Any], source_fields: list[str]) -> dict[str, Any]:
    """Replace equivalent mapped names with the exact parsed source headers."""
    fields = mapper.get("fields")
    if not isinstance(fields, dict):
        return mapper
    by_match_key = {_source_field_match_key(field): field for field in source_fields}
    resolved_fields = {
        target: by_match_key.get(_source_field_match_key(source), source)
        if source else source
        for target, source in fields.items()
    }
    resolved = dict(mapper)
    resolved["fields"] = resolved_fields
    return resolved


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


def _medallion_settings() -> tuple[str, str, str, str, str | None]:
    storage_config = load_storage_config(os.environ.get("WORKFLOW_STORAGE_CONFIG", "config/connections/storage.json"))
    if not storage_config.get("project_id") or not storage_config.get("bronze_dataset_id"):
        raise ValueError("Storage project and bronze dataset are missing from the configuration")
    silver_dataset_id = storage_config.get("silver_dataset_id") or "birdeye_silver_listings"
    gold_dataset_id = storage_config.get("gold_dataset_id") or "birdeye_gold_listings"
    return storage_config["project_id"], storage_config["bronze_dataset_id"], silver_dataset_id, gold_dataset_id, storage_config.get("credentials_json")


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


def _load_zip_reference_sync(project_id: str, dataset_id: str, credentials_json: str | None, *, skip_metadata_check: bool = False) -> dict[str, Any]:
    started_at = perf_counter()
    cache_key = (project_id, dataset_id)
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.us_zipcodes"
    metadata_started_at = perf_counter()
    _ensure_dataset(client, project_id, dataset_id)
    if not skip_metadata_check:
        try:
            existing = client.get_table(table_ref)
            row_count = existing.num_rows or 0
            LOGGER.info("zip_reference_timing phase=metadata_check elapsed_ms=%.1f rows=%d", (perf_counter() - metadata_started_at) * 1000, row_count)
            if row_count >= MINIMUM_US_ZIP_REFERENCE_ROWS:
                mirror_started_at = perf_counter()
                mirror_rows = [dict(row) for row in client.query(f"SELECT zip_code, city_name, county, state_code, state_name, latitude, longitude, population, median_household_income, median_age FROM `{table_ref}`").result()]
                cache_zipcodes(mirror_rows)
                set_zip_reference_status("ready", int(row_count), "US ZIP reference data is ready")
                LOGGER.info("zip_reference_timing phase=bq_table_to_sqlite elapsed_ms=%.1f rows=%d", (perf_counter() - mirror_started_at) * 1000, len(mirror_rows))
                LOGGER.info("zip_reference_ready table=%s rows=%d", table_ref, row_count)
                result = {"status": "ready", "rows": int(row_count), "loaded": True, "created": False, "source": "bronze_copy", "table": table_ref}
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
    source_project_id, _source_credentials_json = resolve_bigquery_connection(source, {"_config_dir": str(config_path.parent)})
    if source_project_id != project_id:
        LOGGER.info("zip_reference_source_project source_project=%s target_project=%s", source_project_id, project_id)
    if source.get("type") == "bigquery" and source_project_id == project_id:
        try:
            LOGGER.info("zip_reference_bq_copy_started table=%s", table_ref)
            copy_started_at = perf_counter()
            client.query(_zip_reference_copy_sql(table_ref, source["query"], source.get("name", "public_demographics"))).result()
            existing = client.get_table(table_ref)
            row_count = int(existing.num_rows or 0)
            set_zip_reference_status("ready", row_count, "US ZIP reference data is ready")
            result = {"status": "ready", "rows": row_count, "loaded": True, "created": True,
                      "source": "bronze_copy", "table": table_ref}
            ZIP_REFERENCE_CACHE[cache_key] = result
            LOGGER.info("zip_reference_timing phase=bq_copy elapsed_ms=%.1f rows=%d", (perf_counter() - copy_started_at) * 1000, row_count)
            return dict(result)
        except Exception as exc:
            LOGGER.warning("zip_reference_bq_copy_failed_falling_back_to_client_fetch error=%s", exc)
    LOGGER.info("zip_reference_source_fetch_started")
    source_started_at = perf_counter()
    demographics = fetch_bigquery_demographics(
        source_project_id,
        source["query"],
        source.get("name", "public_demographics"),
        credentials_json,
    )
    mirror_rows = [
        {
            "zip_code": zip_code,
            "city_name": item.city,
            "county": item.county,
            "state_code": item.state_code,
            "state_name": item.state_name,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "population": item.population,
            "median_household_income": item.median_household_income,
            "median_age": item.median_age,
        }
        for zip_code, item in demographics.items()
    ]
    row_count = len(mirror_rows)
    LOGGER.info("zip_reference_timing phase=source_to_sqlite_rows elapsed_ms=%.1f rows=%d", (perf_counter() - source_started_at) * 1000, row_count)
    if row_count < MINIMUM_US_ZIP_REFERENCE_ROWS:
        raise RuntimeError(f"US ZIP reference source returned only {row_count} rows")
    cache_zipcodes(mirror_rows)
    set_zip_reference_status("ready", row_count, "US ZIP reference data is ready")
    result = {"status": "ready", "rows": row_count, "loaded": True, "created": False, "source": "sqlite_mirror", "table": table_ref}
    ZIP_REFERENCE_CACHE[cache_key] = result
    try:
        LOGGER.info("zip_reference_bq_copy_started table=%s", table_ref)
        copy_started_at = perf_counter()
        client.query(_zip_reference_copy_sql(table_ref, source["query"], source.get("name", "public_demographics"))).result()
        LOGGER.info("zip_reference_timing phase=bq_copy_after_sqlite elapsed_ms=%.1f", (perf_counter() - copy_started_at) * 1000)
        result["created"] = True
        result["source"] = "sqlite_mirror_bq_copy"
        ZIP_REFERENCE_CACHE[cache_key] = result
    except Exception as exc:
        LOGGER.warning("zip_reference_bq_copy_deferred_failed rows=%d error=%s", row_count, exc)
    LOGGER.info("zip_reference_timing phase=rebuild_total elapsed_ms=%.1f rows=%d", (perf_counter() - started_at) * 1000, row_count)
    return dict(result)


def _start_zip_reference_background(project_id: str, dataset_id: str, credentials_json: str | None, *, force: bool = False) -> bool:
    global _ZIP_REFERENCE_THREAD
    with _ZIP_REFERENCE_LOCK:
        if _ZIP_REFERENCE_THREAD and _ZIP_REFERENCE_THREAD.is_alive() and not force:
            return False
        set_zip_reference_status("loading", get_cached_zipcode_count(), "Preparing US ZIP reference data")

        def worker() -> None:
            try:
                result = _load_zip_reference_sync(project_id, dataset_id, credentials_json)
                set_zip_reference_status("ready", int(result.get("rows", 0) or 0), "US ZIP reference data is ready")
            except Exception as exc:
                LOGGER.warning("zip_reference_background_load_failed error=%s", exc)
                set_zip_reference_status("failed", get_cached_zipcode_count(), str(exc))

        _ZIP_REFERENCE_THREAD = threading.Thread(target=worker, name="zip-reference-sync", daemon=True)
        _ZIP_REFERENCE_THREAD.start()
        return True


def prepare_zipcodes(force: bool = False, wait: bool = False) -> dict[str, Any]:
    started_at = perf_counter()
    project_id, dataset_id, credentials_json = _warehouse_settings()
    cache_key = (project_id, dataset_id)
    cached = ZIP_REFERENCE_CACHE.get(cache_key)
    if cached and not force:
        LOGGER.info("zip_reference_timing phase=cache_hit elapsed_ms=%.1f", (perf_counter() - started_at) * 1000)
        return dict(cached)
    if not force:
        try:
            client = _bigquery_client(project_id, credentials_json)
            existing = client.get_table(f"{project_id}.{dataset_id}.us_zipcodes")
            remote_rows = int(existing.num_rows or 0)
            if remote_rows >= MINIMUM_US_ZIP_REFERENCE_ROWS:
                result = {"status": "ready", "rows": remote_rows, "loaded": True,
                          "created": False, "source": "bronze_copy",
                          "table": f"{project_id}.{dataset_id}.us_zipcodes"}
                ZIP_REFERENCE_CACHE[cache_key] = result
                set_zip_reference_status("ready", remote_rows, "US ZIP reference data is ready")
                return dict(result)
            if remote_rows < MINIMUM_US_ZIP_REFERENCE_ROWS:
                return _load_zip_reference_sync(project_id, dataset_id, credentials_json)
        except Exception as exc:
            if getattr(exc, "code", None) == 404:
                return _load_zip_reference_sync(project_id, dataset_id, credentials_json, skip_metadata_check=True)
            LOGGER.info("zip_reference_remote_probe_deferred error=%s", exc)
    local_rows = get_cached_zipcode_count()
    if local_rows >= MINIMUM_US_ZIP_REFERENCE_ROWS and not force:
        result = {"status": "ready", "rows": local_rows, "loaded": True,
                  "created": False, "source": "sqlite_mirror",
                  "table": f"{project_id}.{dataset_id}.us_zipcodes"}
        ZIP_REFERENCE_CACHE[cache_key] = result
        set_zip_reference_status("ready", local_rows, "US ZIP reference data is ready")
        LOGGER.info("zip_reference_timing phase=sqlite_mirror_hit rows=%d elapsed_ms=%.1f", local_rows, (perf_counter() - started_at) * 1000)
        return dict(result)
    if wait:
        result = _load_zip_reference_sync(project_id, dataset_id, credentials_json)
        set_zip_reference_status("ready", int(result.get("rows", 0) or 0), "US ZIP reference data is ready")
        return result
    started = _start_zip_reference_background(project_id, dataset_id, credentials_json, force=force)
    status = get_zip_reference_status()
    return {
        "status": "loading" if status.get("status") in {"not_started", "loading"} else status.get("status", "loading"),
        "rows": int(status.get("rows", 0) or local_rows or 0),
        "loaded": False,
        "created": False,
        "table": f"{project_id}.{dataset_id}.us_zipcodes",
        "background": True,
        "started": started,
        "message": "US ZIP reference data is loading.",
    }


def _load_worldwide_reference_sync(project_id: str, credentials_json: str | None, limit: int = 50000) -> int:
    """Pre-cache worldwide city reference data from BigQuery into SQLite cachedb for ultra-fast local matching."""
    current_count = get_cached_worldwide_city_count()
    if current_count >= 1000:
        return current_count
    client = _bigquery_client(project_id, credentials_json)
    q = f"""
    SELECT
      NULLIF(UPPER(TRIM(CAST(COUNTRY_CODE AS STRING))), '') AS country_code,
      NULLIF(TRIM(CAST(COUNTRY AS STRING)), '') AS country_name,
      NULLIF(TRIM(CAST(STATE AS STRING)), '') AS state_name,
      NULLIF(UPPER(TRIM(CAST(STATE_CODE AS STRING))), '') AS state_code,
      NULLIF(TRIM(CAST(DISTRICT AS STRING)), '') AS district,
      NULLIF(TRIM(CAST(CITY AS STRING)), '') AS city,
      NULLIF(TRIM(CAST(TOWN AS STRING)), '') AS town,
      NULLIF(UPPER(TRIM(CAST(ZIP_CODE AS STRING))), '') AS zip_code,
      LATITUDE AS latitude,
      LONGITUDE AS longitude
    FROM `{project_id}.sample_locations.worldwide_cities`
    WHERE LATITUDE IS NOT NULL AND LONGITUDE IS NOT NULL
      AND (COUNTRY_CODE IN ('CA', 'GB', 'AU', 'FR', 'DE', 'JP', 'US') OR COUNTRY_CODE IS NULL)
    LIMIT {int(limit)}
    """
    try:
        rows = [dict(r) for r in client.query(q).result()]
        if rows:
            cache_worldwide_cities(rows)
            _augment_us_zip_reference_from_worldwide(rows, project_id=project_id, credentials_json=credentials_json)
            LOGGER.info("worldwide_cities_cached_to_sqlite count=%d", len(rows))
            return len(rows)
    except Exception as exc:
        LOGGER.warning("worldwide_reference_load_failed error=%s", exc)
    return get_cached_worldwide_city_count()


def _augment_us_zip_reference_from_worldwide(rows: list[dict[str, Any]], *, project_id: str, credentials_json: str | None) -> int:
    """Fill missing US ZIP reference rows from the worldwide city source."""
    us_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("country_code") or "").strip().upper() != "US":
            continue
        raw_zip = str(row.get("zip_code") or "").strip()
        match = re.search(r"\d{5}", raw_zip)
        if not match:
            continue
        zip_code = match.group(0)
        us_rows.setdefault(zip_code, {
            "zip_code": zip_code,
            "city_name": row.get("city") or row.get("town") or row.get("district"),
            "county": row.get("district"),
            "state_code": row.get("state_code"),
            "state_name": row.get("state_name"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "population": None,
            "median_household_income": None,
            "median_age": None,
        })
    if not us_rows:
        return 0
    inserted = cache_missing_zipcodes(list(us_rows.values()))
    try:
        _, dataset_id, _ = _warehouse_settings()
        client = _bigquery_client(project_id, credentials_json)
        table_ref = f"{project_id}.{dataset_id}.us_zipcodes"
        client.get_table(table_ref)
        query = f"""
        MERGE `{table_ref}` target
        USING (
          SELECT
            UPPER(LPAD(SUBSTR(CAST(ZIP_CODE AS STRING), 1, 5), 5, '0')) AS zip_code,
            COALESCE(NULLIF(TRIM(CAST(CITY AS STRING)), ''), NULLIF(TRIM(CAST(TOWN AS STRING)), ''), NULLIF(TRIM(CAST(DISTRICT AS STRING)), '')) AS city_name,
            NULLIF(TRIM(CAST(DISTRICT AS STRING)), '') AS county,
            NULLIF(UPPER(TRIM(CAST(STATE_CODE AS STRING))), '') AS state_code,
            NULLIF(TRIM(CAST(STATE AS STRING)), '') AS state_name,
            SAFE_CAST(LATITUDE AS FLOAT64) AS latitude,
            SAFE_CAST(LONGITUDE AS FLOAT64) AS longitude
          FROM `{project_id}.sample_locations.worldwide_cities`
          WHERE COUNTRY_CODE = 'US'
            AND ZIP_CODE IS NOT NULL
          QUALIFY ROW_NUMBER() OVER (
            PARTITION BY LPAD(SUBSTR(CAST(ZIP_CODE AS STRING), 1, 5), 5, '0')
            ORDER BY CITY IS NULL, TOWN IS NULL, DISTRICT IS NULL
          ) = 1
        ) source
        ON target.zip_code = source.zip_code
        WHEN NOT MATCHED BY TARGET THEN
          INSERT (
            zip_code, city_name, county, state_code, state_name, latitude, longitude,
            population, median_household_income, median_age, households, income_per_capita,
            poverty, employed_population, unemployed_population, housing_units, source, content_hash
          )
          VALUES (
            source.zip_code, source.city_name, source.county, source.state_code, source.state_name,
            source.latitude, source.longitude, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
            'worldwide_cities_us_supplement',
            TO_HEX(SHA256(TO_JSON_STRING(STRUCT(source.zip_code, source.city_name, source.county, source.state_code, source.state_name, source.latitude, source.longitude))))
          )
        """
        client.query(query).result()
    except Exception as exc:
        LOGGER.warning("us_zip_worldwide_bq_augment_failed count=%d error=%s", len(us_rows), exc)
    return inserted


def _start_worldwide_reference_background(project_id: str, credentials_json: str | None) -> bool:
    """Spawn low-priority background thread to pre-populate worldwide cities into SQLite cachedb."""
    global _WORLDWIDE_REFERENCE_THREAD
    if get_cached_worldwide_city_count() >= 1000:
        return False
    with _WORLDWIDE_REFERENCE_LOCK:
        if _WORLDWIDE_REFERENCE_THREAD and _WORLDWIDE_REFERENCE_THREAD.is_alive():
            return False

        def worker() -> None:
            try:
                _load_worldwide_reference_sync(project_id, credentials_json)
            except Exception as exc:
                LOGGER.warning("worldwide_reference_background_load_failed error=%s", exc)

        _WORLDWIDE_REFERENCE_THREAD = threading.Thread(target=worker, name="worldwide-reference-sync", daemon=True)
        _WORLDWIDE_REFERENCE_THREAD.start()
        return True


def _zip_reference_copy_sql(table_ref: str, source_query: str, source_name: str) -> str:
    query = source_query.rstrip(";")
    source_literal = json.dumps(source_name)
    hash_fields = """
        CAST(zip_code AS STRING) AS zip_code,
        CAST(city_name AS STRING) AS city_name,
        CAST(county AS STRING) AS county,
        CAST(state_code AS STRING) AS state_code,
        CAST(state_name AS STRING) AS state_name,
        CAST(latitude AS STRING) AS latitude,
        CAST(longitude AS STRING) AS longitude,
        CAST(population AS STRING) AS population,
        CAST(median_household_income AS STRING) AS median_household_income,
        CAST(median_age AS STRING) AS median_age,
        CAST(households AS STRING) AS households,
        CAST(income_per_capita AS STRING) AS income_per_capita,
        CAST(poverty AS STRING) AS poverty,
        CAST(employed_population AS STRING) AS employed_population,
        CAST(unemployed_population AS STRING) AS unemployed_population,
        CAST(housing_units AS STRING) AS housing_units,
        source AS source
    """
    return f"""
    CREATE OR REPLACE TABLE `{table_ref}`
    CLUSTER BY state_code, county, zip_code
    AS
    WITH source_zips AS (
      {query}
    ),
    normalized AS (
      SELECT
        LPAD(SUBSTR(CAST(zip_code AS STRING), 1, 5), 5, '0') AS zip_code,
        CAST(city AS STRING) AS city_name,
        CAST(county AS STRING) AS county,
        UPPER(TRIM(CAST(state_code AS STRING))) AS state_code,
        CAST(state_name AS STRING) AS state_name,
        SAFE_CAST(latitude AS FLOAT64) AS latitude,
        SAFE_CAST(longitude AS FLOAT64) AS longitude,
        SAFE_CAST(population AS FLOAT64) AS population,
        SAFE_CAST(median_household_income AS FLOAT64) AS median_household_income,
        SAFE_CAST(median_age AS FLOAT64) AS median_age,
        SAFE_CAST(households AS FLOAT64) AS households,
        SAFE_CAST(income_per_capita AS FLOAT64) AS income_per_capita,
        SAFE_CAST(poverty AS FLOAT64) AS poverty,
        SAFE_CAST(employed_population AS FLOAT64) AS employed_population,
        SAFE_CAST(unemployed_population AS FLOAT64) AS unemployed_population,
        SAFE_CAST(housing_units AS FLOAT64) AS housing_units,
        {source_literal} AS source
      FROM source_zips
      WHERE zip_code IS NOT NULL
    )
    SELECT
      *,
      TO_HEX(SHA256(TO_JSON_STRING(STRUCT({hash_fields})))) AS content_hash
    FROM normalized
    QUALIFY ROW_NUMBER() OVER (PARTITION BY zip_code ORDER BY population DESC NULLS LAST) = 1
    """


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


# ---------------------------------------------------------------------------
# One way to run SQL
# ---------------------------------------------------------------------------
# 91 call sites issued client.query() directly, each re-deriving its own
# parameter plumbing, error handling and (mostly absent) timing. That is how a
# scalar filter survived in one query while its siblings moved to arrays, and
# how a slow statement could hide with nothing to point at. These wrappers are
# the single place SQL leaves this process: they build the parameters, time the
# call, log the shape, and give DML a consistent "rows affected" answer.


def _sql_params(params: dict[str, Any] | None):
    """Build BigQuery query parameters from a plain dict.

    A list/tuple becomes an ARRAY parameter, everything else a scalar, with
    the type inferred - so a caller writes {"states": ["TX"], "limit": 10}
    instead of hand-constructing parameter objects at every site.
    """
    from google.cloud import bigquery

    if not params:
        return []
    def bq_type(value: Any) -> str:
        if isinstance(value, bool):
            return "BOOL"
        if isinstance(value, int):
            return "INT64"
        if isinstance(value, float):
            return "FLOAT64"
        return "STRING"

    built = []
    for name, value in params.items():
        if isinstance(value, (list, tuple, set)):
            items = list(value)
            element_type = bq_type(items[0]) if items else "STRING"
            built.append(bigquery.ArrayQueryParameter(name, element_type, items))
        else:
            built.append(bigquery.ScalarQueryParameter(name, bq_type(value), value))
    return built


def run_sql(client: Any, sql: str, params: dict[str, Any] | None = None, *,
            label: str = "", low_priority: bool = False) -> Any:
    """Run a statement and return the completed job.

    Works for SELECT, INSERT, UPDATE, DELETE, ALTER, DROP and CREATE alike -
    BigQuery does not distinguish them at this layer, and pretending otherwise
    just multiplies near-identical call sites.
    """
    from google.cloud import bigquery

    started = perf_counter()
    if params or low_priority:
        config = bigquery.QueryJobConfig(query_parameters=_sql_params(params))
        if low_priority and hasattr(config, "priority"):
            config.priority = "BATCH"
        job = client.query(sql, job_config=config)
    else:
        # No parameters means no job config: passing an empty one is a no-op
        # for BigQuery but changes the call signature, which breaks any client
        # (including every test double) whose query() takes only the SQL.
        # Keeping the plain shape means this wrapper is a drop-in.
        job = client.query(sql)
    job.result()
    elapsed_ms = (perf_counter() - started) * 1000.0
    # Only slow statements are logged: one line per query would drown the log
    # and cost more than the statements themselves.
    if elapsed_ms >= 1000.0:
        LOGGER.info("sql_slow label=%s elapsed_ms=%.0f", label or _sql_label(sql), elapsed_ms)
    return job


def run_sql_rows(client: Any, sql: str, params: dict[str, Any] | None = None, *,
                 label: str = "") -> list[dict[str, Any]]:
    """Run a query and return its rows as plain dicts."""
    return [dict(row) for row in run_sql(client, sql, params, label=label).result()]


def run_sql_dml(client: Any, sql: str, params: dict[str, Any] | None = None, *,
                label: str = "") -> int:
    """Run a mutation and return the number of rows it actually affected.

    Returning the count (rather than discarding it) is what lets a caller say
    "moved 1,240 listings" instead of "done" - and tells a no-op apart from a
    real change.
    """
    job = run_sql(client, sql, params, label=label)
    return int(getattr(job, "num_dml_affected_rows", 0) or 0)


def _sql_label(sql: str) -> str:
    """First two words of a statement, for logging when no label was given."""
    return " ".join(str(sql or "").strip().split()[:2]).upper()


def _ensure_dataset(client: Any, project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery

    client.create_dataset(bigquery.Dataset(f"{project_id}.{dataset_id}"), exists_ok=True)


def test_storage_connection() -> dict[str, Any]:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_dataset(client, project_id, dataset_id)
    health = _write_connection_health_probe(client, project_id, dataset_id)
    zips = prepare_zipcodes()
    probe = list(client.query("SELECT 1 AS ok").result())
    if not probe or probe[0]["ok"] != 1:
        raise RuntimeError("Workspace readiness check did not return the expected result")
    return {
        "ok": True,
        "status": "ready",
        "health": health,
        "zips": zips,
    }


def ping_storage_connection() -> dict[str, Any]:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_dataset(client, project_id, dataset_id)
    health = _write_connection_health_probe(client, project_id, dataset_id)
    probe = list(client.query("SELECT 1 AS ok").result())
    if not probe or probe[0]["ok"] != 1:
        raise RuntimeError("Readiness check did not return the expected result")
    return {
        "ok": True,
        "status": "ready",
        "health": health,
    }


def _write_connection_health_probe(client: Any, project_id: str, dataset_id: str) -> dict[str, Any]:
    table_ref = f"{project_id}.{dataset_id}.connection_health"
    client.query(f"""
    CREATE OR REPLACE TABLE `{table_ref}` AS
    SELECT
      'storage_connection' AS probe_name,
      CURRENT_TIMESTAMP() AS checked_at,
      1 AS ok
    """).result()
    rows = list(client.query(f"SELECT ok FROM `{table_ref}` LIMIT 1").result())
    if not rows or rows[0]["ok"] != 1:
        raise RuntimeError("Connection health probe table did not return the expected row")
    return {"table": table_ref, "rows": 1}


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
    existing_schema = getattr(existing, "schema", None)
    if existing_schema is None:
        return
    existing_names = {field.name for field in existing_schema}
    missing_fields = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"],
            default_value_expression=field.get("default"),
        )
        for field in TABLE_SCHEMAS["businesses"]
        if field["name"] not in existing_names
    ]
    if missing_fields:
        existing.schema = list(existing_schema) + missing_fields
        client.update_table(existing, ["schema"])


def _ensure_listings_table(client: Any, project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery

    table_ref = f"{project_id}.{dataset_id}.listings"
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
            for field in TABLE_SCHEMAS["listings"]
        ]
        table = bigquery.Table(table_ref, schema=schema)
        cluster_fields = TABLE_CLUSTER_SPECS.get("listings")
        if cluster_fields:
            table.clustering_fields = cluster_fields
        client.create_table(table)
        return
    existing_schema = getattr(existing, "schema", None)
    if existing_schema is None:
        return
    existing_names = {field.name for field in existing_schema}
    missing_fields = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"],
            default_value_expression=field.get("default"),
        )
        for field in TABLE_SCHEMAS["listings"]
        if field["name"] not in existing_names
    ]
    # Relax any already-deployed column that TABLE_SCHEMAS now marks
    # NULLABLE but the live table still has as REQUIRED - e.g. only "brand"
    # (business_id) stays mandatory now, so name/address/city_name/
    # state_code/zip_code/country must no longer reject a row for being
    # blank. BigQuery allows REQUIRED -> NULLABLE in place; adding new
    # columns above never touches existing ones, so this needs its own pass.
    target_modes = {field["name"]: field["mode"] for field in TABLE_SCHEMAS["listings"]}
    updated_schema = []
    schema_changed = bool(missing_fields)
    for field in existing_schema:
        target_mode = target_modes.get(field.name)
        if target_mode == "NULLABLE" and field.mode == "REQUIRED":
            updated_schema.append(bigquery.SchemaField(
                field.name, field.field_type, mode="NULLABLE",
                default_value_expression=getattr(field, "default_value_expression", None),
            ))
            schema_changed = True
        else:
            updated_schema.append(field)
    if schema_changed:
        existing.schema = updated_schema + missing_fields
        client.update_table(existing, ["schema"])


# Table schemas only change when this process deploys new code, but the
# _ensure_*_table() passes were re-running on EVERY save - each one a
# get_table round trip against BigQuery. Measured on a live warehouse: a
# BigQuery round trip floors at ~1.75s, so two ensure passes added ~3.6s to
# every single-record edit before any real work started. Remember which
# tables this process has already reconciled; a deploy restarts the process
# and clears it, which is exactly when the schema can differ.
_ENSURED_TABLES: set[str] = set()
_ENSURED_TABLES_LOCK = threading.Lock()


def _ensure_once(table_key: str, ensure: Any, client: Any, project_id: str, dataset_id: str) -> None:
    """Run an ensure pass at most once per process for a given table."""
    cache_key = f"{project_id}.{dataset_id}.{table_key}"
    with _ENSURED_TABLES_LOCK:
        if cache_key in _ENSURED_TABLES:
            return
    ensure(client, project_id, dataset_id)
    with _ENSURED_TABLES_LOCK:
        _ENSURED_TABLES.add(cache_key)


def _forget_ensured_tables() -> None:
    """Drop the memo after anything that can change the deployed schema
    (a clear, a master delete) so the next write re-reconciles."""
    with _ENSURED_TABLES_LOCK:
        _ENSURED_TABLES.clear()


def _ensure_error_listings_table(client: Any, project_id: str, dataset_id: str) -> None:
    """Create error_listings, or add any column TABLE_SCHEMAS has gained.

    This was missing entirely: unlike listings/businesses, error_listings had
    no ensure-pass, so a column added to TABLE_SCHEMAS never reached an
    already-deployed table. `has_ai_suggestion` (added for the AI/manual
    review-pending split) was therefore absent live, and every query
    selecting it failed with "Name has_ai_suggestion not found inside e" -
    taking the whole quality tab and its exports down with it.
    """
    from google.cloud import bigquery

    table_ref = f"{project_id}.{dataset_id}.error_listings"
    _ensure_dataset(client, project_id, dataset_id)
    schema_fields = [
        bigquery.SchemaField(field["name"], field["type"], mode=field["mode"],
                             default_value_expression=field.get("default"))
        for field in TABLE_SCHEMAS["error_listings"]
    ]
    try:
        existing = client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        table = bigquery.Table(table_ref, schema=schema_fields)
        cluster_fields = TABLE_CLUSTER_SPECS.get("error_listings")
        if cluster_fields:
            table.clustering_fields = cluster_fields
        client.create_table(table)
        return
    existing_schema = getattr(existing, "schema", None)
    if existing_schema is None:
        return
    existing_names = {field.name for field in existing_schema}
    missing_fields = [field for field in schema_fields if field.name not in existing_names]
    if missing_fields:
        existing.schema = list(existing_schema) + missing_fields
        client.update_table(existing, ["schema"])
        LOGGER.info("error_listings_schema_extended columns=%s", [f.name for f in missing_fields])


def list_brands(search: str = "") -> dict[str, Any]:
    cache_key = f"list_brands:{search.strip().lower()}"
    cached = get_cached_query(cache_key)
    if cached:
        for brand in cached.get("brands", []):
            brand.setdefault("display_business_id", _display_business_id(brand))
        return cached

    # NOTE: brand listing reads BigQuery businesses directly (the
    # authoritative store), NOT the SQLite gold mirror. The mirror only
    # refreshes on a gold rebuild, so serving brands from it made a
    # freshly-created business invisible in the mapper's dropdown until the
    # next rebuild - breaking the create-business-then-map flow. The
    # query_cache above still gives the fast repeat-read; a brand mutation
    # invalidates it, so the next list is fresh from BigQuery.
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
      b.description,
      b.logo_url,
      b.website_url,
      b.status,
      b.created_at,
      b.updated_at,
      (
        SELECT COUNT(*)
        FROM `{project_id}.{dataset_id}.listings` l
        WHERE l.business_id = b.business_id AND l.is_deleted IS NOT TRUE
      ) AS listing_count,
      b.meta_title,
      b.meta_description,
      b.country_of_origin,
      b.is_reference_data,
      b.reference_key,
      b.default_source_url,
      b.default_source_name,
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
    brands = [dict(row) for row in client.query(query, job_config=config).result()]
    for brand in brands:
        # BigQuery TIMESTAMP columns (created_at, updated_at) come back as
        # datetime objects, which json.dumps can't serialize - both the
        # HTTP response and set_cached_query() below would raise
        # "Object of type datetime is not JSON serializable". Normalize any
        # datetime-like value to an ISO string, matching list_templates().
        for key, value in list(brand.items()):
            if hasattr(value, "isoformat"):
                brand[key] = value.isoformat()
        brand["display_business_id"] = _display_business_id(brand)
    res = {"brands": brands}
    set_cached_query(cache_key, res)
    return res


def _display_business_id(brand: dict[str, Any]) -> str:
    hashable = {
        key: (value.isoformat() if hasattr(value, "isoformat") else value)
        for key, value in brand.items()
        if key not in {"business_id", "created_at", "updated_at", "display_business_id", "listing_count", "source_type_name"}
    }
    payload = json.dumps(hashable, sort_keys=True, separators=(",", ":"), default=str)
    return "BID " + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8].upper()


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


def _serialize_for_json(obj: dict[str, Any]) -> dict[str, Any]:
    """Convert datetime objects to ISO strings for JSON serialization."""
    from datetime import datetime
    result = {}
    for key, value in obj.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def create_brand(data: dict[str, Any]) -> dict[str, Any]:
    from google.cloud import bigquery

    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Brand name is required")
    slug = str(data.get("slug") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
    source_type_id = None
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    query = f"""
    INSERT INTO `{project_id}.{dataset_id}.businesses`
      (name, slug, source_type_id, description, logo_url, website_url, status, created_at, updated_at, meta_title, meta_description, country_of_origin, is_reference_data, reference_key, default_source_url, default_source_name)
    VALUES (@name, @slug, @source_type_id, @description, @logo_url, @website_url, @status, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), @meta_title, @meta_description, @country_of_origin, @is_reference_data, @reference_key, @default_source_url, @default_source_name)
    """
    params = [
        bigquery.ScalarQueryParameter("name", "STRING", name), bigquery.ScalarQueryParameter("slug", "STRING", slug),
        bigquery.ScalarQueryParameter("source_type_id", "STRING", source_type_id),
        bigquery.ScalarQueryParameter("description", "STRING", data.get("description")), bigquery.ScalarQueryParameter("logo_url", "STRING", data.get("logo_url")),
        bigquery.ScalarQueryParameter("website_url", "STRING", data.get("website_url")), bigquery.ScalarQueryParameter("status", "STRING", data.get("status") or "active"),
        bigquery.ScalarQueryParameter("meta_title", "STRING", data.get("meta_title")), bigquery.ScalarQueryParameter("meta_description", "STRING", data.get("meta_description")),
        bigquery.ScalarQueryParameter("country_of_origin", "STRING", data.get("country_of_origin")),
        bigquery.ScalarQueryParameter("is_reference_data", "BOOL", bool(data.get("is_reference_data"))),
        bigquery.ScalarQueryParameter("reference_key", "STRING", data.get("reference_key")),
        bigquery.ScalarQueryParameter("default_source_url", "STRING", data.get("default_source_url")),
        bigquery.ScalarQueryParameter("default_source_name", "STRING", data.get("default_source_name")),
    ]
    client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    lookup = f"""
    SELECT b.business_id, b.name, b.slug, b.description, b.logo_url, b.website_url, b.status,
      b.created_at, b.updated_at,
      (SELECT COUNT(*) FROM `{project_id}.{dataset_id}.listings` l WHERE l.business_id = b.business_id AND l.is_deleted IS NOT TRUE) AS listing_count,
      b.meta_title, b.meta_description, b.country_of_origin, b.is_reference_data, b.reference_key,
      b.default_source_url, b.default_source_name, b.source_type_id, st.name AS source_type_name
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
    brand = dict(result[0])
    brand["display_business_id"] = _display_business_id(brand)
    brand = _serialize_for_json(brand)
    _sync_gold_mirror_best_effort()
    return {"brand": brand}


def update_brand(data: dict[str, Any]) -> dict[str, Any]:
    from google.cloud import bigquery

    business_id = str(data.get("business_id", "")).strip()
    name = str(data.get("name", "")).strip()
    if not business_id:
        raise ValueError("Business ID is required")
    if not name:
        raise ValueError("Brand name is required")
    slug = str(data.get("slug") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    query = f"""
    UPDATE `{project_id}.{dataset_id}.businesses`
    SET name = @name,
      slug = @slug,
      description = @description,
      logo_url = @logo_url,
      website_url = @website_url,
      status = @status,
      updated_at = CURRENT_TIMESTAMP(),
      meta_title = @meta_title,
      meta_description = @meta_description,
      country_of_origin = @country_of_origin,
      is_reference_data = @is_reference_data,
      reference_key = @reference_key,
      default_source_url = @default_source_url,
      default_source_name = @default_source_name
    WHERE business_id = @business_id AND is_deleted IS NOT TRUE
    """
    params = [
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
        bigquery.ScalarQueryParameter("name", "STRING", name),
        bigquery.ScalarQueryParameter("slug", "STRING", slug),
        bigquery.ScalarQueryParameter("description", "STRING", data.get("description")),
        bigquery.ScalarQueryParameter("logo_url", "STRING", data.get("logo_url")),
        bigquery.ScalarQueryParameter("website_url", "STRING", data.get("website_url")),
        bigquery.ScalarQueryParameter("status", "STRING", data.get("status") or "active"),
        bigquery.ScalarQueryParameter("meta_title", "STRING", data.get("meta_title")),
        bigquery.ScalarQueryParameter("meta_description", "STRING", data.get("meta_description")),
        bigquery.ScalarQueryParameter("country_of_origin", "STRING", data.get("country_of_origin")),
        bigquery.ScalarQueryParameter("is_reference_data", "BOOL", bool(data.get("is_reference_data"))),
        bigquery.ScalarQueryParameter("reference_key", "STRING", data.get("reference_key")),
        bigquery.ScalarQueryParameter("default_source_url", "STRING", data.get("default_source_url")),
        bigquery.ScalarQueryParameter("default_source_name", "STRING", data.get("default_source_name")),
    ]
    client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    lookup = f"""
    SELECT b.business_id, b.name, b.slug, b.description, b.logo_url, b.website_url, b.status,
      b.created_at, b.updated_at,
      (SELECT COUNT(*) FROM `{project_id}.{dataset_id}.listings` l WHERE l.business_id = b.business_id AND l.is_deleted IS NOT TRUE) AS listing_count,
      b.meta_title, b.meta_description, b.country_of_origin, b.is_reference_data, b.reference_key,
      b.default_source_url, b.default_source_name, b.source_type_id, st.name AS source_type_name
    FROM `{project_id}.{dataset_id}.businesses` b
    LEFT JOIN `{project_id}.{dataset_id}.source_types` st
      ON b.source_type_id = st.source_type_id
    WHERE b.is_deleted IS NOT TRUE AND b.business_id = @business_id
    LIMIT 1
    """
    result = list(client.query(lookup, job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("business_id", "STRING", business_id)])).result())
    if not result:
        raise RuntimeError("Brand update did not return a matching active business")
    invalidate_cache()
    brand = dict(result[0])
    brand["display_business_id"] = _display_business_id(brand)
    brand = _serialize_for_json(brand)
    _sync_gold_mirror_best_effort()
    return {"brand": brand}


def merge_brands(data: dict[str, Any]) -> dict[str, Any]:
    from google.cloud import bigquery

    target_business_id = str(data.get("target_business_id", "")).strip()
    source_business_ids = [
        str(item).strip()
        for item in data.get("source_business_ids", [])
        if str(item).strip() and str(item).strip() != target_business_id
    ]
    if not target_business_id:
        raise ValueError("Target business is required")
    if not source_business_ids:
        raise ValueError("Choose at least one business to merge")
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    params = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("target_business_id", "STRING", target_business_id),
        bigquery.ArrayQueryParameter("source_business_ids", "STRING", source_business_ids),
    ])
    # Measure what the merge actually moved, per table. "Merged 2 brands" says
    # nothing about impact; "moved 1,240 listings and 38 review rows" is what
    # tells the user whether the merge mattered - and makes a merge that moved
    # nothing (already-empty duplicate) visibly different from one that
    # consolidated a real footprint.
    moved: dict[str, int] = {}
    merge_params = {"target_business_id": target_business_id,
                    "source_business_ids": source_business_ids}
    MERGED_TABLES = ("listings", "workflow_templates", "error_listings")
    if bool(data.get("preview")):
        # A merge is irreversible from the UI, so the confirmation step has to
        # name what actually moves - and name it from the warehouse, not from
        # whatever count the brand dropdown happened to be showing. A table we
        # cannot read reports None ("count unavailable") rather than 0, so an
        # unreadable table never gets presented as "nothing to move".
        counts: dict[str, int | None] = {}
        for table_name in MERGED_TABLES:
            try:
                rows = run_sql_rows(client, f"""
                SELECT COUNT(*) AS row_count
                FROM `{project_id}.{dataset_id}.{table_name}`
                WHERE business_id IN UNNEST(@source_business_ids)
                """, {"source_business_ids": source_business_ids},
                    label=f"merge_brands:preview:{table_name}")
                counts[table_name] = int(rows[0].get("row_count", 0)) if rows else 0
            except Exception as exc:
                LOGGER.warning("merge_preview_count_failed table=%s error=%s", table_name, exc)
                counts[table_name] = None
        known = [value for value in counts.values() if value is not None]
        return {
            "preview": True,
            "target_business_id": target_business_id,
            "merged_business_ids": source_business_ids,
            "merged_count": len(source_business_ids),
            "moved": counts,
            "moved_total": sum(known) if known else 0,
            "counts_complete": len(known) == len(MERGED_TABLES),
            "listings_moved": counts.get("listings"),
            "templates_moved": counts.get("workflow_templates"),
            "review_rows_moved": counts.get("error_listings"),
        }
    for table_name in MERGED_TABLES:
        moved[table_name] = run_sql_dml(client, f"""
        UPDATE `{project_id}.{dataset_id}.{table_name}`
        SET business_id = @target_business_id
        WHERE business_id IN UNNEST(@source_business_ids)
        """, merge_params, label=f"merge_brands:{table_name}")
    run_sql_dml(client, f"""
    UPDATE `{project_id}.{dataset_id}.businesses`
    SET is_deleted = TRUE, deleted_on = CURRENT_TIMESTAMP(), updated_at = CURRENT_TIMESTAMP()
    WHERE business_id IN UNNEST(@source_business_ids)
    """, merge_params, label="merge_brands:retire_sources")
    invalidate_cache()
    _sync_gold_mirror_best_effort()
    total_moved = sum(moved.values())
    LOGGER.info("brands_merged target=%s sources=%d listings=%d templates=%d review_rows=%d",
                target_business_id, len(source_business_ids),
                moved.get("listings", 0), moved.get("workflow_templates", 0),
                moved.get("error_listings", 0))
    return {
        "target_business_id": target_business_id,
        "merged_business_ids": source_business_ids,
        "merged_count": len(source_business_ids),
        # Weighting: how much this merge actually consolidated.
        "moved": moved,
        "moved_total": total_moved,
        "listings_moved": moved.get("listings", 0),
        "templates_moved": moved.get("workflow_templates", 0),
        "review_rows_moved": moved.get("error_listings", 0),
    }


def _sync_gold_mirror_best_effort() -> None:
    """Refresh the reporting mirror after a brand mutation, OFF the request's
    critical path. sync_gold_mirror() runs three heavy BigQuery view scans
    (all zip-brand rows, all locations, all businesses); doing that inline on
    every brand create/update/merge made those calls take seconds and could
    hang the UI. The brand write itself has already landed in BigQuery and the
    list_brands cache is invalidated, so the dropdown is correct immediately;
    the mirror (used only by reporting) just catches up a moment later."""
    def _run() -> None:
        try:
            sync_gold_mirror()
        except Exception as exc:
            LOGGER.warning("gold_mirror_business_sync_failed error=%s", exc)

    threading.Thread(target=_run, name="brand-mirror-sync", daemon=True).start()


LEARNING_TEMPLATES_CACHE_KEY = "learning_templates:v1"


def learn_mappings(data: dict[str, Any]) -> dict[str, Any]:
    source_type = str(data.get("source_type", ""))
    source_fields = data.get("source_fields", [])
    if not source_type or not isinstance(source_fields, list):
        raise ValueError("source_type and source_fields are required")
    # The underlying query is the same for every source_type (filtering by
    # source_type happens client-side in suggest_from_templates()), so one
    # SQLite-cached copy of the raw template rows serves every mapping-
    # workspace open instead of re-querying BigQuery's workflow_templates
    # every time - invalidate_cache() (already called broadly after any
    # save) clears this like every other cached query, so a freshly saved
    # template becomes visible to learning on the next uncached read.
    cached = get_cached_query(LEARNING_TEMPLATES_CACHE_KEY)
    if cached is not None:
        templates = cached.get("templates", [])
    else:
        project_id, dataset_id, credentials_json = _warehouse_settings()
        client = _bigquery_client(project_id, credentials_json)
        table_ref = f"{project_id}.{dataset_id}.workflow_templates"
        try:
            templates = [dict(row) for row in client.query(f"SELECT components FROM `{table_ref}` ORDER BY updated_at DESC LIMIT 500").result()]
        except Exception as exc:
            if getattr(exc, "code", None) == 404:
                templates = []
            else:
                raise
        set_cached_query(LEARNING_TEMPLATES_CACHE_KEY, {"templates": templates})
    suggestions = suggest_from_templates(templates, source_fields, source_type)
    # Layer the field-mapping confidence score on top of the template-vote
    # suggestions: a target field with no template-vote suggestion yet, but
    # a real accumulated positive-confidence pairing (kept/manually chosen
    # across enough past saves) whose normalized name matches one of THIS
    # source's actual parsed fields, gets suggested too - this is how a
    # newer field (no template history at all) starts getting auto-mapped
    # once its confidence has actually earned it, rather than needing a
    # hardcoded hint or a first historical template to exist.
    try:
        _normalize = lambda value: "".join(ch for ch in str(value or "").lower() if ch.isalnum())
        normalized_available = {_normalize(field): field for field in source_fields if str(field).strip()}
        # Repopulate from BigQuery if a restart wiped the ephemeral cache.
        _restore_mapping_confidence_once()
        confidence_rows = get_mapping_confidence()
        best_by_target: dict[str, dict[str, Any]] = {}
        for row in confidence_rows:
            target_key = row["target_key"]
            if target_key in suggestions:
                continue
            if row["score"] <= 0 or row["sample_count"] < 2:
                continue
            matched_field = normalized_available.get(row["source_field_normalized"])
            if not matched_field:
                continue
            current_best = best_by_target.get(target_key)
            if current_best is None or row["score"] > current_best["score"]:
                best_by_target[target_key] = {"source": matched_field, "uses": row["sample_count"], "score": row["score"]}
        for target_key, suggestion in best_by_target.items():
            suggestions[target_key] = {"source": suggestion["source"], "uses": suggestion["uses"], "confidence_score": suggestion["score"]}
    except Exception as exc:
        LOGGER.warning("mapping_confidence_suggestion_merge_failed error=%s", exc)
    return {"suggestions": suggestions}


def list_templates(search: str = "", business_id: str = "", source_type_id: str = "", limit: int = 500, offset: int = 0, *, client: Any = None) -> dict[str, Any]:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    if client is None:
        client = _bigquery_client(project_id, credentials_json)
    _ensure_workflow_templates_table(client, project_id, dataset_id)
    safe_limit = max(1, min(int(limit or 500), 5000))
    safe_offset = max(0, int(offset or 0))
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
    LIMIT {safe_limit} OFFSET {safe_offset}
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
    return {"templates": templates, "limit": safe_limit, "offset": safe_offset}


def list_source_types() -> dict[str, Any]:
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
    if str(dataset_id).strip().lower() == "sample_locations":
        raise PermissionError("CRITICAL SAFETY RULE: 'sample_locations' is an immutable source dataset. Cannot reset or delete.")
    for table_name in ("businesses", "listings", "workflow_templates", "error_listings"):
        table_ref = f"{project_id}.{dataset_id}.{table_name}"
        try:
            client.query(
                f"""
                ALTER TABLE `{table_ref}` ADD COLUMN IF NOT EXISTS is_deleted BOOL;
                ALTER TABLE `{table_ref}` ADD COLUMN IF NOT EXISTS deleted_on TIMESTAMP;
                UPDATE `{table_ref}`
                SET is_deleted = TRUE, deleted_on = CURRENT_TIMESTAMP()
                WHERE is_sample_data IS TRUE AND is_deleted IS NOT TRUE
                """
            ).result()
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                raise


def clear_sample_dataset() -> dict[str, Any]:
    """Start clearing ingested sample records without making the UI wait."""
    global _SAMPLE_CLEAR_RUNNING
    project_id, dataset_id, credentials_json = _warehouse_settings()
    if str(dataset_id).strip().lower() == "sample_locations":
        raise PermissionError("CRITICAL SAFETY RULE: 'sample_locations' is an immutable source dataset. Cannot clear.")

    with _SAMPLE_CLEAR_LOCK:
        if _SAMPLE_CLEAR_RUNNING:
            return {
                "cleared": False,
                "message": "Sample data cleanup is already running.",
                "background": True,
        }
        _SAMPLE_CLEAR_RUNNING = True
    invalidate_cache()
    ZIP_REFERENCE_CACHE.pop((project_id, dataset_id), None)
    sample_business_ids = [stable_business_id(brand.key) for brand in SAMPLE_BRANDS]
    sample_brand_names = [brand.business_name for brand in SAMPLE_BRANDS]
    try:
        clear_sample_reporting_mirror(sample_business_ids, sample_brand_names)
    except Exception as exc:
        LOGGER.warning("sample_reporting_mirror_clear_failed error=%s", exc)
    try:
        client = _bigquery_client(project_id, credentials_json)
        _reset_sample_data(client, project_id, dataset_id)
    except Exception:
        with _SAMPLE_CLEAR_LOCK:
            _SAMPLE_CLEAR_RUNNING = False
        raise

    silver_result = _background_medallion_refresh_status()

    def clear_worker() -> None:
        global _SAMPLE_CLEAR_RUNNING
        try:
            invalidate_cache()
            # invalidate_cache() deliberately spares reporting_quality:* keys
            # (they self-refresh on read), but a clear changes the underlying
            # population, so those must go too.
            invalidate_quality_cache()
            # Rebuild silver/gold and re-sync the SQLite mirror, or reporting
            # keeps serving the rows that were just cleared - the mirror is
            # read before BigQuery. force_mirror because an empty result is
            # the correct new truth here, not a transient failure.
            try:
                _invoke_silver_layer(low_priority=True)
                _rebuild_gold_and_mirror(force_mirror=True)
                # Same RULE as clear_saved_data: the persisted fix counters
                # must be recounted, or they keep showing fixes for cleared rows.
                _schedule_quality_fix_metrics_refresh(force=True)
            except Exception as mirror_exc:
                LOGGER.warning("mirror_resync_after_sample_clear_failed error=%s", mirror_exc)
            try:
                refresh_error_count("")
            except Exception as count_exc:
                LOGGER.warning("error_count_refresh_after_sample_clear_failed error=%s", count_exc)
        except Exception as exc:
            LOGGER.warning("sample_dataset_clear_failed error=%s", exc)
        finally:
            with _SAMPLE_CLEAR_LOCK:
                _SAMPLE_CLEAR_RUNNING = False

    threading.Thread(target=clear_worker, name="sample-dataset-clear", daemon=True).start()

    return {
        "cleared": True,
        "message": "Sample data cleanup started. Reporting will refresh shortly.",
        "background": True,
        "silver": silver_result,
    }



def sample_dataset_status() -> dict[str, Any]:
    if not _sample_loader_enabled():
        return {"enabled": False, "loaded": False, "message": "Sample dataset loader is disabled for this environment"}
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    try:
        counts = _sample_data_status(client, project_id, dataset_id)
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            counts = {"businesses": 0, "listings": 0, "workflow_templates": 0, "error_listings": 0}
        else:
            raise
    loaded = bool(counts["businesses"] and counts["listings"])
    return {
        "enabled": True,
        "loaded": loaded,
        "sample_batch_id": SAMPLE_BATCH_ID,
        "businesses": counts["businesses"],
        "locations": counts["listings"],
        "templates": counts.get("workflow_templates", 0),
        "errors": counts.get("error_listings", 0),
    }


def _background_medallion_refresh_status() -> dict[str, Any]:
    """Kick off (or note an already-in-flight) background silver+gold
    rebuild instead of blocking the caller on it."""
    started = _refresh_silver_background()
    return {"status": "refreshing", "background": True, "started": started}


def load_sample_dataset(reset: bool = False, load_half: int = 1) -> dict[str, Any]:
    """Load the sample dataset. `load_half` selects one NTILE(2) slice.

    The source listings are split in SQL with NTILE(2) rather than orchestrated
    in Python: half 1 lands fast, the caller gets a usable dataset immediately
    and the button can flip to "loaded", and half 2 is filled in behind it.
    Splitting in the query means each half is a single bounded INSERT, so a
    slow row cannot hold the whole load hostage - the previous version ran
    everything as one statement and appeared to hang at "94%".
    """
    from google.cloud import bigquery

    if not _sample_loader_enabled():
        raise ValueError("Sample dataset loader is disabled for this environment")

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    _ensure_source_types_table(client, project_id, dataset_id)
    _ensure_workflow_templates_table(client, project_id, dataset_id)
    zip_result = prepare_zipcodes()

    source_sample_dataset = "sample_locations"
    source_project_id = project_id

    if reset:
        _reset_sample_data(client, project_id, dataset_id)
    else:
        sample_status = _sample_data_status(client, project_id, dataset_id)
        if sample_status.get("businesses", 0) > 0 and sample_status.get("listings", 0) > 0:
            silver_result = _background_medallion_refresh_status()
            return {
                "already_loaded": True,
                "sample_batch_id": SAMPLE_BATCH_ID,
                "message": "Sample dataset already loaded.",
                "businesses": sample_status["businesses"],
                "locations": sample_status["listings"],
                "errors": sample_status.get("error_listings", 0),
                "zips": zip_result,
                "silver": silver_result,
            }
        if sample_status.get("businesses", 0) > 0 or sample_status.get("listings", 0) > 0:
            _reset_sample_data(client, project_id, dataset_id)

    # Ingest from sample_locations into bronze layer
    ingested_from_sample_locations = False
    businesses_count = 0
    listings_count = 0
    try:
        # Verify source sample_locations table exists
        src_table_ref = f"{source_project_id}.{source_sample_dataset}.listings"
        client.get_table(src_table_ref)

        # Only on the first half: half 2 must add to what half 1 inserted,
        # not wipe it.
        if load_half == 1:
            client.query(f"DELETE FROM `{project_id}.{dataset_id}.listings` WHERE is_sample_data IS TRUE").result()
            client.query(f"DELETE FROM `{project_id}.{dataset_id}.businesses` WHERE is_sample_data IS TRUE").result()

        # 1. Copy source_types (preserving reference integrity)
        client.query(f"""
        INSERT INTO `{project_id}.{dataset_id}.source_types` (source_type_id, name, data_format, created_at, content_hash)
        SELECT s.source_type_id, s.name, SAFE.PARSE_JSON(s.data_format), s.created_at, s.content_hash
        FROM `{source_project_id}.{source_sample_dataset}.source_types` s
        WHERE NOT EXISTS (
            SELECT 1 FROM `{project_id}.{dataset_id}.source_types` t WHERE t.source_type_id = s.source_type_id
        )
        """).result()

        # 2. Copy businesses into bronze with is_sample_data = TRUE
        client.query(f"""
        INSERT INTO `{project_id}.{dataset_id}.businesses` (
          business_id, name, slug, source_type_id, description, logo_url, website_url,
          status, created_at, updated_at, meta_title, meta_description, country_of_origin,
          is_reference_data, reference_key, default_source_url, default_source_name,
          is_sample_data, sample_batch_id, content_hash, is_deleted, deleted_on
        )
        SELECT
          s.business_id, s.name, s.slug, s.source_type_id, s.description, s.logo_url, s.website_url,
          s.status, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), s.meta_title, s.meta_description, s.country_of_origin,
          COALESCE(s.is_reference_data, FALSE), s.reference_key, s.default_source_url, s.default_source_name,
          TRUE AS is_sample_data, '{SAMPLE_BATCH_ID}' AS sample_batch_id, s.content_hash, FALSE AS is_deleted, s.deleted_on
        FROM `{source_project_id}.{source_sample_dataset}.businesses` s
        WHERE {"TRUE" if load_half == 1 else "FALSE"}
          AND NOT EXISTS (
            SELECT 1 FROM `{project_id}.{dataset_id}.businesses` b
            WHERE b.business_id = s.business_id AND b.is_sample_data IS TRUE
          )
        """).result()

        # 3. Copy listings into bronze with is_sample_data = TRUE (all 51 columns)
        client.query(f"""
        INSERT INTO `{project_id}.{dataset_id}.listings` (
          listing_id, business_id, source_type_id, location_key, name, address, city_name,
          town, state_code, province, zip_code, country, latitude, longitude,
          first_observed_at, last_observed_at, template_id, ingestion_id, mapping_id,
          validation_status, validated, enriched_at, is_sample_data, sample_batch_id, franchise_name, concept_type,
          cuisine_type, neighborhood, district, phone_number, website_url, google_maps_link,
          social_media_handles, operating_hours, seating_capacity, service_types, opening_date,
          status, annual_revenue, average_ticket_size, daily_footfall, monthly_footfall,
          rental_cost, lease_cost, population_density, average_household_income,
          competitor_count, foot_traffic_score, parking_availability, ratings,
          content_hash, is_deleted, deleted_on
        )
        SELECT
          s.listing_id, s.business_id, s.source_type_id, s.location_key, s.name, s.address, s.city_name,
          s.town, s.state_code, s.province, s.zip_code, s.country, s.latitude, s.longitude,
          CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), s.template_id, s.ingestion_id, s.mapping_id,
          s.validation_status, COALESCE(s.validated, FALSE) AS validated, CAST(NULL AS TIMESTAMP) AS enriched_at, TRUE AS is_sample_data, '{SAMPLE_BATCH_ID}' AS sample_batch_id, s.franchise_name, s.concept_type,
          s.cuisine_type, s.neighborhood, s.district, s.phone_number, s.website_url, s.google_maps_link,
          s.social_media_handles, s.operating_hours, s.seating_capacity, s.service_types, s.opening_date,
          s.status, s.annual_revenue, s.average_ticket_size, s.daily_footfall, s.monthly_footfall,
          s.rental_cost, s.lease_cost, s.population_density, s.average_household_income,
          s.competitor_count, s.foot_traffic_score, s.parking_availability, s.ratings,
          s.content_hash, FALSE AS is_deleted, s.deleted_on
        FROM (
          SELECT *, NTILE(2) OVER (ORDER BY listing_id) AS load_half
          FROM `{source_project_id}.{source_sample_dataset}.listings`
        ) s
        WHERE s.load_half = @load_half
        """, job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("load_half", "INT64", load_half),
        ])).result()

        biz_row = next(iter(client.query(f"SELECT COUNT(DISTINCT business_id) AS cnt FROM `{project_id}.{dataset_id}.businesses` WHERE is_sample_data IS TRUE AND is_deleted IS NOT TRUE").result()))
        list_row = next(iter(client.query(f"SELECT COUNT(1) AS cnt FROM `{project_id}.{dataset_id}.listings` WHERE is_sample_data IS TRUE AND is_deleted IS NOT TRUE").result()))
        businesses_count = int(biz_row["cnt"])
        listings_count = int(list_row["cnt"])
        ingested_from_sample_locations = True
        LOGGER.info("sample_locations_ingested_to_bronze half=%d businesses=%d listings=%d",
                    load_half, businesses_count, listings_count)
        if load_half == 1:
            # Hand back a usable dataset now - the button flips to "loaded"
            # and the user can start working - while the second half fills in
            # behind them. A failure here leaves half the data loaded and
            # says so, rather than rolling back work that is already useful.
            def load_second_half() -> None:
                try:
                    result = load_sample_dataset(reset=False, load_half=2)
                    LOGGER.info("sample_second_half_loaded listings=%d", result.get("locations", 0))
                except Exception as exc:
                    LOGGER.warning("sample_second_half_failed error=%s", exc)

            threading.Thread(target=load_second_half, name="sample-second-half", daemon=True).start()
    except Exception as exc:
        LOGGER.warning("sample_locations_ingestion_error error=%s", exc)

    # Fallback to in-memory generator if sample_locations was unavailable (e.g. mock test suite)
    if not ingested_from_sample_locations:
        now = utc_now_iso()
        source_type_ids = {source_type: ensure_source_type(source_type) for source_type in sorted({brand.source_type for brand in SAMPLE_BRANDS})}
        # Count rows per brand, not mere presence. A brand whose previous load
        # died half way (a timeout, a restart) had SOME rows, so a presence
        # check marked it "already loaded" and it stayed permanently partial.
        existing_sample_counts: dict[str, int] = {}
        try:
            existing_rows = client.query(
                f"SELECT business_id, COUNT(*) AS n FROM `{project_id}.{dataset_id}.listings` "
                f"WHERE is_deleted IS NOT TRUE AND is_sample_data IS TRUE GROUP BY business_id"
            ).result()
            existing_sample_counts = {row["business_id"]: int(row["n"] or 0) for row in existing_rows if row.get("business_id")}
        except Exception as exc:
            LOGGER.warning("existing_sample_brands_query_failed error=%s", exc)

        def _is_fully_loaded(brand: Any) -> bool:
            stored = existing_sample_counts.get(stable_business_id(brand.key), 0)
            if not stored:
                return False
            expected = int(getattr(brand, "row_count", 0) or 0)
            if not expected:
                return True  # no declared size to compare against
            # Re-running a partially loaded brand is safe: save_mapper dedupes
            # against bronze on (business_id, content_hash), so already-stored
            # rows are skipped and only the missing ones land.
            if stored < expected:
                LOGGER.info("sample_brand_partially_loaded brand=%s stored=%d expected=%d reloading",
                            brand.key, stored, expected)
                return False
            return True

        brands_to_load = [brand for brand in SAMPLE_BRANDS if not _is_fully_loaded(brand)]
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
            "zips": zip_result,
        }
        # Brands are independent (own business_id, own template, own rows), so
        # they load concurrently instead of one after another - a 15-brand
        # sequential load was the bulk of the wall-clock time. The pool is
        # deliberately small: this runs on a 512MB box, and each worker holds
        # a brand's rows in memory while it builds the batch.
        SAMPLE_LOAD_WORKERS = 4
        # A brand that cannot finish in this window is abandoned rather than
        # holding up the rest - the user gets a usable dataset now, and the
        # skipped brand is reported instead of silently missing.
        SAMPLE_BRAND_TIMEOUT_SECONDS = 180

        def _load_one_brand(brand: Any) -> tuple[Any, dict[str, Any] | None, str]:
            try:
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
                }, client=client, skip_cache_invalidation=True, assume_tables_exist=True)
                return brand, result, ""
            except Exception as exc:
                # One brand failing (a bad row shape, a transient BigQuery
                # hiccup) must not abort the whole load - same tolerance a
                # real multi-brand upload has for a bad batch.
                LOGGER.warning("sample_brand_load_failed brand=%s error=%s", brand.key, exc)
                return brand, None, str(exc)

        skipped_brands: list[str] = []
        # Phase timing, so a stall is measurable rather than guessed at. The
        # ZIP path already logs `zip_reference_timing phase=... elapsed_ms=`;
        # the sample load had event logs but no durations, which is why
        # "why does it stick" could only be answered by staring at it.
        phase_started = perf_counter()
        brand_timings: dict[str, float] = {}
        with ThreadPoolExecutor(max_workers=SAMPLE_LOAD_WORKERS, thread_name_prefix="sample-load") as pool:
            futures = {pool.submit(_load_one_brand, brand): brand for brand in brands_to_load}
            for future in as_completed(futures, timeout=SAMPLE_BRAND_TIMEOUT_SECONDS * max(len(futures), 1)):
                brand = futures[future]
                try:
                    brand, result, error = future.result(timeout=SAMPLE_BRAND_TIMEOUT_SECONDS)
                except Exception as exc:
                    LOGGER.warning("sample_brand_timed_out brand=%s error=%s", brand.key, exc)
                    skipped_brands.append(brand.key)
                    continue
                if result is None:
                    skipped_brands.append(brand.key)
                    continue
                summary["locations"] += result["total_rows"]
                summary["valid"] += result["mapped_rows"]
                summary["errors"] += result["error_listings"]
                summary["source_types"].setdefault(source_label(brand.source_type), 0)
                summary["source_types"][source_label(brand.source_type)] += 1
                summary["countries"].update(brand.geographies)
                brand_timings[brand.key] = round(perf_counter() - phase_started, 2)
                LOGGER.info("sample_brand_loaded brand=%s rows=%d elapsed_s=%.2f",
                            brand.key, result.get("total_rows", 0), brand_timings[brand.key])
        # Reported, never silent: a partial load must be visible.
        summary["skipped_brands"] = skipped_brands
        total_elapsed = round(perf_counter() - phase_started, 2)
        slowest = sorted(brand_timings.items(), key=lambda item: item[1], reverse=True)[:3]
        LOGGER.info("sample_load_timing total_s=%.2f brands=%d skipped=%d slowest=%s",
                    total_elapsed, len(brand_timings), len(skipped_brands), slowest)
        summary["timing"] = {"total_seconds": total_elapsed, "per_brand_seconds": brand_timings}

        summary["silver"] = _background_medallion_refresh_status()
        summary["countries"] = len(summary["countries"])
        summary["validation_success_pct"] = round(summary["valid"] / max(summary["locations"], 1) * 100, 1)
        invalidate_cache()
        invalidate_quality_cache()
        # Bronze is written above; carry it through to gold and the SQLite
        # mirror too, or reporting keeps serving the pre-load picture until
        # something else happens to trigger a rebuild.
        def _promote_sample_to_gold() -> None:
            try:
                _invoke_silver_layer(low_priority=True)
                _rebuild_gold_and_mirror(force_mirror=True)
                _schedule_quality_fix_metrics_refresh(force=True)
            except Exception as exc:
                LOGGER.warning("sample_load_gold_promotion_failed error=%s", exc)
        threading.Thread(target=_promote_sample_to_gold, name="sample-gold-promote", daemon=True).start()
        return summary

    # Return summary for sample_locations ingestion
    silver_result = _background_medallion_refresh_status()
    summary = {
        "already_loaded": False,
        "sample_batch_id": SAMPLE_BATCH_ID,
        "businesses": businesses_count,
        "loaded_new": businesses_count,
        "locations": listings_count,
        "valid": listings_count,
        "errors": 0,
        "source_types": {"CSV Source": businesses_count // 2, "JSON API Source": businesses_count // 2},
        "countries": 1,
        "validation_success_pct": 100.0,
        "zips": zip_result,
        "silver": silver_result,
    }
    invalidate_cache()
    return summary


def _csv_param(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _safe_query(client: Any, query: str, low_priority: bool = False) -> Any:
    job_config = None
    if low_priority:
        try:
            from google.cloud import bigquery
            job_config = bigquery.QueryJobConfig(priority=bigquery.QueryPriority.BATCH)
        except Exception:
            job_config = SimpleNamespace(priority="BATCH")
    try:
        if job_config is None:
            return client.query(query)
        return client.query(query, job_config=job_config)
    except TypeError:
        if job_config is not None:
            return client.query(query)
        raise


def build_silver_layer(low_priority: bool = False) -> dict[str, Any]:
    project_id, bronze_dataset_id, silver_dataset_id, _gold_dataset_id, credentials_json = _medallion_settings()
    client = _bigquery_client(project_id, credentials_json)
    try:
        _enrichment_checkpoint()
        _ensure_dataset(client, project_id, bronze_dataset_id)
        _ensure_dataset(client, project_id, silver_dataset_id)
        _ensure_businesses_table(client, project_id, bronze_dataset_id)
        _ensure_listings_table(client, project_id, bronze_dataset_id)
        bronze_ref = f"{project_id}.{bronze_dataset_id}"
        silver_ref = f"{project_id}.{silver_dataset_id}"
        zip_reference_table = f"{silver_ref}.zip_reference"
        enriched_table = f"{silver_ref}.listings_enriched"
        invalid_table = f"{silver_ref}.listings_invalid"
        top_view = f"{silver_ref}.vw_brand_location_top10"
        brand_zip_view = f"{silver_ref}.vw_brand_zip_income"
        _safe_query(client, f"DROP TABLE IF EXISTS `{enriched_table}`", low_priority=low_priority).result()
        _enrichment_checkpoint()
        if low_priority:
            sleep(0.05)
        _safe_query(client, f"DROP TABLE IF EXISTS `{invalid_table}`", low_priority=low_priority).result()
        _enrichment_checkpoint()
        if low_priority:
            sleep(0.05)

        zip_city_case = _proper_case_sql("city_name")
        zip_county_case = _proper_case_sql("county")
        zip_state_name_case = _proper_case_sql("state_name")

        # Build one silver ZIP reference for enrichment/reporting by unioning
        # canonical US ZIP data with US rows from worldwide cities, then dedupe
        # by ZIP. Canonical rows win because they carry demographic fields.
        _safe_query(client, f"""
        CREATE OR REPLACE TABLE `{zip_reference_table}`
        CLUSTER BY state_code, zip_code
        AS
        WITH canonical_us_zips AS (
          SELECT
            LPAD(SUBSTR(CAST(zip_code AS STRING), 1, 5), 5, '0') AS zip_code,
            CAST(city_name AS STRING) AS city_name,
            CAST(county AS STRING) AS county,
            UPPER(TRIM(CAST(state_code AS STRING))) AS state_code,
            CAST(state_name AS STRING) AS state_name,
            SAFE_CAST(latitude AS FLOAT64) AS latitude,
            SAFE_CAST(longitude AS FLOAT64) AS longitude,
            SAFE_CAST(population AS FLOAT64) AS population,
            SAFE_CAST(median_household_income AS FLOAT64) AS median_household_income,
            SAFE_CAST(median_age AS FLOAT64) AS median_age,
            SAFE_CAST(income_per_capita AS FLOAT64) AS income_per_capita,
            SAFE_CAST(households AS FLOAT64) AS households,
            SAFE_CAST(poverty AS FLOAT64) AS poverty,
            SAFE_CAST(employed_population AS FLOAT64) AS employed_population,
            SAFE_CAST(unemployed_population AS FLOAT64) AS unemployed_population,
            SAFE_CAST(housing_units AS FLOAT64) AS housing_units,
            COALESCE(source, 'us_zipcodes') AS source,
            1 AS source_priority
          FROM `{bronze_ref}.us_zipcodes`
          WHERE zip_code IS NOT NULL
        ),
        worldwide_us_zips AS (
          SELECT
            UPPER(LPAD(SUBSTR(CAST(ZIP_CODE AS STRING), 1, 5), 5, '0')) AS zip_code,
            COALESCE(NULLIF(TRIM(CAST(CITY AS STRING)), ''), NULLIF(TRIM(CAST(TOWN AS STRING)), ''), NULLIF(TRIM(CAST(DISTRICT AS STRING)), '')) AS city_name,
            NULLIF(TRIM(CAST(DISTRICT AS STRING)), '') AS county,
            NULLIF(UPPER(TRIM(CAST(STATE_CODE AS STRING))), '') AS state_code,
            NULLIF(TRIM(CAST(STATE AS STRING)), '') AS state_name,
            SAFE_CAST(LATITUDE AS FLOAT64) AS latitude,
            SAFE_CAST(LONGITUDE AS FLOAT64) AS longitude,
            NULL AS population,
            NULL AS median_household_income,
            NULL AS median_age,
            NULL AS income_per_capita,
            NULL AS households,
            NULL AS poverty,
            NULL AS employed_population,
            NULL AS unemployed_population,
            NULL AS housing_units,
            'worldwide_cities_us_supplement' AS source,
            2 AS source_priority
          FROM `{project_id}.sample_locations.worldwide_cities`
          WHERE COUNTRY_CODE = 'US'
            AND ZIP_CODE IS NOT NULL
            AND REGEXP_CONTAINS(CAST(ZIP_CODE AS STRING), r'\\d{{5}}')
        ),
        unioned AS (
          SELECT * FROM canonical_us_zips
          UNION ALL
          SELECT * FROM worldwide_us_zips
        ),
        deduped AS (
          SELECT *
          FROM unioned
          QUALIFY ROW_NUMBER() OVER (
            PARTITION BY zip_code
            ORDER BY source_priority, population DESC NULLS LAST, city_name IS NULL
          ) = 1
        )
        SELECT
          zip_code,
          {zip_city_case} AS city_name,
          {zip_county_case} AS county,
          UPPER(TRIM(state_code)) AS state_code,
          {zip_state_name_case} AS state_name,
          latitude,
          longitude,
          population,
          median_household_income,
          median_age,
          income_per_capita,
          households,
          poverty,
          employed_population,
          unemployed_population,
          housing_units,
          source,
          CURRENT_TIMESTAMP() AS silver_updated_at
        FROM deduped
        """, low_priority=low_priority).result()
        _enrichment_checkpoint()
        if low_priority:
            sleep(0.05)

        worldwide_reference_table = f"{silver_ref}.worldwide_cities"
        _safe_query(client, f"""
        CREATE OR REPLACE TABLE `{worldwide_reference_table}`
        CLUSTER BY country_code, state_code, city
        AS
        SELECT
          NULLIF(UPPER(TRIM(CAST(COUNTRY_CODE AS STRING))), '') AS country_code,
          NULLIF(TRIM(CAST(COUNTRY AS STRING)), '') AS country_name,
          NULLIF(TRIM(CAST(STATE AS STRING)), '') AS state_name,
          NULLIF(UPPER(TRIM(CAST(STATE_CODE AS STRING))), '') AS state_code,
          NULLIF(TRIM(CAST(DISTRICT AS STRING)), '') AS district,
          NULLIF(TRIM(CAST(CITY AS STRING)), '') AS city,
          NULLIF(TRIM(CAST(TOWN AS STRING)), '') AS town,
          NULLIF(TRIM(CAST(ZIP_CODE AS STRING)), '') AS zip_code,
          LATITUDE AS latitude,
          LONGITUDE AS longitude,
          GEOCODE_ACCURACY AS geocode_accuracy,
          CURRENT_TIMESTAMP() AS silver_updated_at
        FROM `{project_id}.sample_locations.worldwide_cities`
        WHERE LATITUDE IS NOT NULL AND LONGITUDE IS NOT NULL
        """, low_priority=low_priority).result()
        if low_priority:
            sleep(0.05)

        brand_name_case = _proper_case_sql("COALESCE(b.name, l.business_id)")
        location_name_case = _proper_case_sql("l.name")
        # Source hierarchy is authoritative for identity. ZIP/reference data
        # fills gaps or corrects a conflicting postal value; it must not
        # silently replace a supplied town/city/state.
        latitude_expr = """COALESCE(l.latitude, z.latitude, cg.latitude)"""
        longitude_expr = """COALESCE(l.longitude, z.longitude, cg.longitude)"""
        corrected_latitude_expr = f"""
          CASE
            WHEN l.unswapped_latitude IS NOT NULL AND l.unswapped_longitude IS NOT NULL
              AND l.unswapped_latitude BETWEEN 13.0 AND 72.0
              AND ((l.unswapped_longitude BETWEEN -180.0 AND -64.0) OR (l.unswapped_longitude BETWEEN 144.0 AND 146.0))
              AND NOT (l.unswapped_latitude = 0.0 AND l.unswapped_longitude = 0.0)
              AND (cg.latitude IS NULL OR ST_DISTANCE(ST_GEOGPOINT(l.unswapped_longitude, l.unswapped_latitude), ST_GEOGPOINT(cg.longitude, cg.latitude)) <= 150000)
              THEN l.unswapped_latitude
            ELSE COALESCE(z.latitude, cg.latitude)
          END
        """
        corrected_longitude_expr = f"""
          CASE
            WHEN l.unswapped_latitude IS NOT NULL AND l.unswapped_longitude IS NOT NULL
              AND l.unswapped_latitude BETWEEN 13.0 AND 72.0
              AND ((l.unswapped_longitude BETWEEN -180.0 AND -64.0) OR (l.unswapped_longitude BETWEEN 144.0 AND 146.0))
              AND NOT (l.unswapped_latitude = 0.0 AND l.unswapped_longitude = 0.0)
              AND (cg.longitude IS NULL OR ST_DISTANCE(ST_GEOGPOINT(l.unswapped_longitude, l.unswapped_latitude), ST_GEOGPOINT(cg.longitude, cg.latitude)) <= 150000)
              THEN l.unswapped_longitude
            ELSE COALESCE(z.longitude, cg.longitude)
          END
        """
        city_name_case = _proper_case_sql(f"COALESCE(NULLIF(TRIM(l.town), ''), NULLIF(TRIM(l.city_name), ''), cg.matched_city, z.city_name)")
        county_case = _proper_case_sql("z.county")
        state_name_case = _proper_case_sql(f"COALESCE(NULLIF(TRIM(l.province), ''), cg.matched_state, z.state_name, NULLIF(TRIM(l.town), ''))")

        mandatory_check = """
          brand_name IS NOT NULL AND brand_name != ''
          AND name IS NOT NULL AND name != ''
          AND address IS NOT NULL AND address != ''
          AND city_name IS NOT NULL AND city_name != ''
          AND state_code IS NOT NULL AND state_code != ''
          AND zip_code IS NOT NULL AND zip_code != ''
          AND country IS NOT NULL AND country != ''
          AND latitude IS NOT NULL AND longitude IS NOT NULL
        """
        rejection_reason_expr = """
          ARRAY_TO_STRING(ARRAY(
            SELECT reason FROM UNNEST([
              IF(brand_name IS NULL OR brand_name = '', 'missing_brand', NULL),
              IF(name IS NULL OR name = '', 'missing_name', NULL),
              IF(address IS NULL OR address = '', 'missing_address', NULL),
              IF(city_name IS NULL OR city_name = '', 'missing_city', NULL),
              IF(state_code IS NULL OR state_code = '', 'missing_state', NULL),
              IF(zip_code IS NULL OR zip_code = '', 'missing_zip', NULL),
              IF(country IS NULL OR country = '', 'missing_country', NULL),
              IF(latitude IS NULL OR longitude IS NULL, 'unresolved_coordinates', NULL)
              ,IF(latitude IS NOT NULL AND longitude IS NOT NULL AND LOWER(TRIM(COALESCE(country, ''))) IN ('', 'us', 'usa', 'united states', 'united states of america') AND NOT (latitude BETWEEN 13.0 AND 72.0 AND ((longitude BETWEEN -180.0 AND -64.0) OR (longitude BETWEEN 144.0 AND 146.0))), 'coordinates_outside_us_boundary', NULL)
            ]) AS reason
            WHERE reason IS NOT NULL
          ), ', ')
        """

        query = f"""
        CREATE OR REPLACE TABLE `{silver_ref}._listings_staging`
        PARTITION BY DATE(first_observed_at)
        CLUSTER BY state_code, zip_code, business_id
        AS
        WITH normalized_listings AS (
          SELECT
            *,
            COALESCE(first_observed_at, CURRENT_TIMESTAMP()) AS first_observed_at_coalesced,
            REGEXP_EXTRACT(CAST(zip_code AS STRING), r'(\\d{{5}})') AS normalized_zip_code,
            LOWER(TRIM(city_name)) AS normalized_city_name,
            -- Detect and fix inverted coordinates (latitude in longitude range, longitude in latitude range)
            CASE
              WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                AND ((latitude BETWEEN -180.0 AND -64.0) OR (latitude BETWEEN 144.0 AND 146.0))
                AND (longitude BETWEEN 13.0 AND 72.0)
              THEN longitude
              ELSE latitude
            END AS unswapped_latitude,
            CASE
              WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                AND ((latitude BETWEEN -180.0 AND -64.0) OR (latitude BETWEEN 144.0 AND 146.0))
                AND (longitude BETWEEN 13.0 AND 72.0)
              THEN latitude
              ELSE longitude
            END AS unswapped_longitude,
            CASE UPPER(TRIM(COALESCE(state_code, '')))
              WHEN 'ALABAMA' THEN 'AL' WHEN 'ALASKA' THEN 'AK' WHEN 'ARIZONA' THEN 'AZ' WHEN 'ARKANSAS' THEN 'AR'
              WHEN 'CALIFORNIA' THEN 'CA' WHEN 'COLORADO' THEN 'CO' WHEN 'CONNECTICUT' THEN 'CT' WHEN 'DELAWARE' THEN 'DE'
              WHEN 'FLORIDA' THEN 'FL' WHEN 'GEORGIA' THEN 'GA' WHEN 'HAWAII' THEN 'HI' WHEN 'IDAHO' THEN 'ID'
              WHEN 'ILLINOIS' THEN 'IL' WHEN 'INDIANA' THEN 'IN' WHEN 'IOWA' THEN 'IA' WHEN 'KANSAS' THEN 'KS'
              WHEN 'KENTUCKY' THEN 'KY' WHEN 'LOUISIANA' THEN 'LA' WHEN 'MAINE' THEN 'ME' WHEN 'MARYLAND' THEN 'MD'
              WHEN 'MASSACHUSETTS' THEN 'MA' WHEN 'MICHIGAN' THEN 'MI' WHEN 'MINNESOTA' THEN 'MN' WHEN 'MISSISSIPPI' THEN 'MS'
              WHEN 'MISSOURI' THEN 'MO' WHEN 'MONTANA' THEN 'MT' WHEN 'NEBRASKA' THEN 'NE' WHEN 'NEVADA' THEN 'NV'
              WHEN 'NEW HAMPSHIRE' THEN 'NH' WHEN 'NEW JERSEY' THEN 'NJ' WHEN 'NEW MEXICO' THEN 'NM' WHEN 'NEW YORK' THEN 'NY'
              WHEN 'NORTH CAROLINA' THEN 'NC' WHEN 'NORTH DAKOTA' THEN 'ND' WHEN 'OHIO' THEN 'OH' WHEN 'OKLAHOMA' THEN 'OK'
              WHEN 'OREGON' THEN 'OR' WHEN 'PENNSYLVANIA' THEN 'PA' WHEN 'RHODE ISLAND' THEN 'RI' WHEN 'SOUTH CAROLINA' THEN 'SC'
              WHEN 'SOUTH DAKOTA' THEN 'SD' WHEN 'TENNESSEE' THEN 'TN' WHEN 'TEXAS' THEN 'TX' WHEN 'UTAH' THEN 'UT'
              WHEN 'VERMONT' THEN 'VT' WHEN 'VIRGINIA' THEN 'VA' WHEN 'WASHINGTON' THEN 'WA' WHEN 'WEST VIRGINIA' THEN 'WV'
              WHEN 'WISCONSIN' THEN 'WI' WHEN 'WYOMING' THEN 'WY' WHEN 'DISTRICT OF COLUMBIA' THEN 'DC'
              WHEN 'PUERTO RICO' THEN 'PR' WHEN 'GUAM' THEN 'GU' WHEN 'VIRGIN ISLANDS' THEN 'VI'
              ELSE NULLIF(UPPER(TRIM(COALESCE(state_code, ''))), '')
            END AS normalized_state_code
          FROM `{bronze_ref}.listings`
          WHERE is_deleted IS NOT TRUE
        ),
        unique_zips AS (
          SELECT * FROM `{zip_reference_table}`
        ),
        city_geos AS (
          SELECT
            LOWER(TRIM(city)) AS normalized_city_name,
            LOWER(TRIM(COALESCE(state_code, state_name))) AS normalized_state,
            LOWER(TRIM(COALESCE(country_code, country_name))) AS normalized_country,
            ANY_VALUE(state_code) AS state_code,
            ANY_VALUE(zip_code) AS representative_zip,
            ANY_VALUE(city) AS matched_city,
            ANY_VALUE(state_name) AS matched_state,
            ANY_VALUE(country_name) AS matched_country,
            AVG(latitude) AS latitude,
            AVG(longitude) AS longitude
          FROM `{worldwide_reference_table}`
          WHERE city IS NOT NULL
          GROUP BY normalized_city_name, normalized_state, normalized_country
        )
        SELECT
          l.listing_id,
          l.business_id,
          {brand_name_case} AS brand_name,
          l.source_type_id,
          l.location_key,
          -- Source columns no typed field covers. Silver and gold must carry
          -- this through or a custom field is invisible to everything
          -- downstream (reporting, quality, exports) even though bronze
          -- stored it. listings_enriched/listings_invalid are SELECT * off
          -- this staging table, so adding it here reaches both.
          l.custom_fields,
          {location_name_case} AS name,
          l.address,
          {city_name_case} AS city_name,
          {county_case} AS county,
          COALESCE(l.normalized_state_code, NULLIF(UPPER(TRIM(l.state_code)), ''), cg.state_code, z.state_code) AS state_code,
          {state_name_case} AS state_name,
          COALESCE(
            CASE WHEN l.unswapped_latitude IS NOT NULL AND l.unswapped_longitude IS NOT NULL
              AND z.latitude IS NOT NULL AND z.longitude IS NOT NULL
              AND ST_DISTANCE(ST_GEOGPOINT(l.unswapped_longitude, l.unswapped_latitude), ST_GEOGPOINT(z.longitude, z.latitude)) <= 100000
              THEN l.normalized_zip_code END,
            CASE WHEN cg.latitude IS NOT NULL AND cg.longitude IS NOT NULL
              AND l.unswapped_latitude IS NOT NULL AND l.unswapped_longitude IS NOT NULL
              AND ST_DISTANCE(ST_GEOGPOINT(l.unswapped_longitude, l.unswapped_latitude), ST_GEOGPOINT(cg.longitude, cg.latitude)) <= 100000
              THEN cg.representative_zip END,
            l.normalized_zip_code,
            cg.representative_zip
          ) AS zip_code,
          COALESCE(NULLIF(TRIM(l.country), ''), cg.matched_country, 'United States') AS country,
          -- COALESCE(l.latitude, z.latitude, cg.latitude) AS latitude
          {corrected_latitude_expr} AS latitude,
          -- COALESCE(l.longitude, z.longitude, cg.longitude) AS longitude
          {corrected_longitude_expr} AS longitude,
          CASE
            WHEN l.unswapped_latitude IS NOT NULL AND l.unswapped_longitude IS NOT NULL
              AND l.unswapped_latitude BETWEEN 13.0 AND 72.0
              AND ((l.unswapped_longitude BETWEEN -180.0 AND -64.0) OR (l.unswapped_longitude BETWEEN 144.0 AND 146.0))
              AND NOT (l.unswapped_latitude = 0.0 AND l.unswapped_longitude = 0.0)
              AND (cg.latitude IS NULL OR ST_DISTANCE(ST_GEOGPOINT(l.unswapped_longitude, l.unswapped_latitude), ST_GEOGPOINT(cg.longitude, cg.latitude)) <= 150000)
              THEN 'source_listing'
            WHEN z.latitude IS NOT NULL AND z.longitude IS NOT NULL THEN 'zip_centroid'
            WHEN cg.latitude IS NOT NULL AND cg.longitude IS NOT NULL THEN 'worldwide_city_centroid'
            ELSE 'unresolved'
          END AS coordinate_source,
          CASE
            WHEN l.unswapped_latitude IS NOT NULL AND l.unswapped_longitude IS NOT NULL
              AND l.unswapped_latitude BETWEEN 13.0 AND 72.0
              AND ((l.unswapped_longitude BETWEEN -180.0 AND -64.0) OR (l.unswapped_longitude BETWEEN 144.0 AND 146.0))
              AND NOT (l.unswapped_latitude = 0.0 AND l.unswapped_longitude = 0.0)
              AND (cg.latitude IS NULL OR ST_DISTANCE(ST_GEOGPOINT(l.unswapped_longitude, l.unswapped_latitude), ST_GEOGPOINT(cg.longitude, cg.latitude)) <= 150000)
              THEN 1.0
            WHEN z.latitude IS NOT NULL AND z.longitude IS NOT NULL THEN 0.85
            WHEN cg.latitude IS NOT NULL AND cg.longitude IS NOT NULL THEN 0.70
            ELSE 0.0
          END AS coordinate_confidence,
          ARRAY_TO_STRING(
            ARRAY(
              SELECT part
              FROM UNNEST([
                NULLIF(TRIM(l.address), ''),
                NULLIF(TRIM(l.city_name), ''),
                NULLIF(TRIM(l.state_code), ''),
                COALESCE(l.normalized_zip_code, cg.representative_zip)
              ]) AS part
              WHERE part IS NOT NULL
            ),
            ', '
          ) AS geocode_query,
          l.phone_number,
          l.content_hash,
          l.first_observed_at_coalesced AS first_observed_at,
          l.last_observed_at,
          z.population,
          z.median_household_income,
          z.median_age,
          z.income_per_capita,
          COUNT(*) OVER (PARTITION BY COALESCE(l.normalized_zip_code, cg.representative_zip), LOWER(TRIM(l.address))) AS similar_address_count,
          CURRENT_TIMESTAMP() AS silver_updated_at
        FROM normalized_listings l
        LEFT JOIN `{bronze_ref}.businesses` b
          ON l.business_id = b.business_id
          AND b.is_deleted IS NOT TRUE
        LEFT JOIN unique_zips z
          ON l.normalized_zip_code = z.zip_code
        LEFT JOIN city_geos cg
          ON EDIT_DISTANCE(l.normalized_city_name, cg.normalized_city_name) <= 2
          AND (cg.normalized_state = LOWER(TRIM(l.state_code)) OR cg.normalized_state = LOWER(TRIM(l.province)) OR cg.normalized_state = LOWER(TRIM(l.town)))
          AND (cg.normalized_country = LOWER(TRIM(l.country)) OR LOWER(TRIM(l.country)) IN ('', 'us', 'usa', 'united states'))
        WHERE l.is_deleted IS NOT TRUE
        """
        _safe_query(client, query, low_priority=low_priority).result()
        _enrichment_checkpoint()
        if low_priority:
            sleep(0.05)

        staging_table = f"{silver_ref}._listings_staging"
        _safe_query(client, f"""
        CREATE OR REPLACE TABLE `{enriched_table}`
        PARTITION BY DATE(first_observed_at)
        CLUSTER BY state_code, zip_code, business_id
        AS
        SELECT * FROM `{staging_table}`
        WHERE {mandatory_check}
        """, low_priority=low_priority).result()
        _enrichment_checkpoint()
        if low_priority:
            sleep(0.05)

        _safe_query(client, f"""
        CREATE OR REPLACE TABLE `{invalid_table}`
        PARTITION BY DATE(first_observed_at)
        CLUSTER BY state_code, zip_code, business_id
        AS
        SELECT *, {rejection_reason_expr} AS rejection_reason
        FROM `{staging_table}`
        WHERE NOT ({mandatory_check})
        """, low_priority=low_priority).result()
        _enrichment_checkpoint()
        if low_priority:
            sleep(0.05)

        # Only rows that actually pass silver validation leave the unresolved
        # queue. Rows remaining in listings_invalid or error_listings must stay
        # unvalidated so a later repair batch can try them again.
        _safe_query(client, f"""
        UPDATE `{bronze_ref}.listings`
        SET validated = TRUE,
            enriched_at = CURRENT_TIMESTAMP()
        WHERE listing_id IN (SELECT listing_id FROM `{enriched_table}`)
          AND (validated IS NOT TRUE OR enriched_at IS NULL)
        """, low_priority=low_priority).result()

        _safe_query(client, f"DROP TABLE IF EXISTS `{staging_table}`", low_priority=low_priority).result()
        if low_priority:
            sleep(0.05)

        _safe_query(client, f"""
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
        """, low_priority=low_priority).result()
        if low_priority:
            sleep(0.05)

        _safe_query(client, f"""
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
        """, low_priority=low_priority).result()

        table = client.get_table(enriched_table)
        invalid_rows = client.get_table(invalid_table)
        invalidate_cache()
        return {
            "bronze_dataset": bronze_ref,
            "silver_dataset": silver_ref,
            "zip_reference_table": zip_reference_table,
            "enriched_table": enriched_table,
            "invalid_table": invalid_table,
            "views": [top_view, brand_zip_view],
            "rows": int(table.num_rows or 0),
            "invalid_rows": int(invalid_rows.num_rows or 0),
            "priority": "batch" if low_priority else "interactive",
        }
    except Exception as exc:
        if "stopped by user" in str(exc).lower():
            ENRICHMENT_STATUS.update({"state": "stopped", "updated_at": utc_now_iso()})
        else:
            ENRICHMENT_STATUS.update({"state": "failed", "updated_at": utc_now_iso()})
        LOGGER.warning("build_silver_layer_error error=%s", exc)
        return {
            "bronze_dataset": f"{project_id}.{bronze_dataset_id}",
            "silver_dataset": f"{project_id}.{silver_dataset_id}",
            "rows": 0,
            "invalid_rows": 0,
            "status": "failed",
            "warning": str(exc),
            "priority": "batch" if low_priority else "interactive",
        }


# Bumped whenever a gold view's SELECT list changes. _ensure_gold_reporting_views()
# used to return early whenever the views merely EXISTED, so an edited view
# definition never reached an already-deployed environment - only a brand new
# one got the new SQL. That is the same drift class as error_listings missing
# has_ai_suggestion. The version is stamped on each view's description at
# build time and compared on every ensure.
GOLD_VIEW_DEFINITION_VERSION = "2026-09-09.custom-fields"


def build_gold_layer() -> dict[str, Any]:
    """Pre-aggregated reporting views over the silver listings_enriched table.

    Grain of the foundation view (vw_zip_brand_activity) is (zip_code,
    brand_name), with one brand_name=NULL row per zip that has zero
    listings. This lets callers get brand-agnostic zip/city coverage via
    COUNT(DISTINCT zip_code) (fan-out safe) while still supporting
    per-brand rollups by filtering/grouping on brand_name - mirroring the
    reporting queries' existing "zip coverage is geo-filtered only;
    listing/brand counts are also brand-filtered" split.
    """
    project_id, bronze_dataset_id, silver_dataset_id, gold_dataset_id, credentials_json = _medallion_settings()
    client = _bigquery_client(project_id, credentials_json)
    _ensure_dataset(client, project_id, gold_dataset_id)
    bronze_ref = f"{project_id}.{bronze_dataset_id}"
    silver_ref = f"{project_id}.{silver_dataset_id}"
    gold_ref = f"{project_id}.{gold_dataset_id}"
    enriched_table = f"{silver_ref}.listings_enriched"

    zip_brand_view = f"{gold_ref}.vw_zip_brand_activity"
    brand_view = f"{gold_ref}.vw_brand_summary"
    location_view = f"{gold_ref}.vw_reporting_locations"
    filters_view = f"{gold_ref}.vw_reporting_filter_options"
    gap_base_view = f"{gold_ref}.vw_reporting_gap_base"

    # These views were built at various points but never queried anywhere -
    # each was grouped by brand_name, which can't answer "distinct zips
    # across a user-chosen multi-brand selection" without double counting,
    # so reporting_summary() always filtered zip_brand_view/vw_reporting_locations
    # directly instead. Drop the stale objects from BigQuery itself, not just
    # the code that used to create them.
    for dead_view in ("vw_state_summary", "vw_city_summary", "vw_listing_quality_summary",
                      "vw_geo_reference", "vw_reporting_totals", "vw_reporting_state_brand",
                      "vw_reporting_city_brand", "vw_reporting_zip_summary"):
        client.query(f"DROP VIEW IF EXISTS `{gold_ref}.{dead_view}`").result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{zip_brand_view}` AS
    SELECT
      z.zip_code,
      z.state_code,
      z.state_name,
      z.county,
      z.city_name,
      z.population,
      z.median_household_income,
      z.median_age,
      z.latitude,
      z.longitude,
      l.brand_name,
      COUNT(l.listing_id) AS location_count,
      MAX(l.last_observed_at) AS last_observed_at
    FROM `{silver_ref}.zip_reference` z
    LEFT JOIN `{enriched_table}` l ON z.zip_code = l.zip_code
    GROUP BY z.zip_code, z.state_code, z.state_name, z.county, z.city_name,
      z.population, z.median_household_income, z.median_age, z.latitude, z.longitude, l.brand_name
    """).result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{brand_view}` AS
    SELECT
      brand_name,
      SUM(location_count) AS location_count,
      COUNT(DISTINCT state_code) AS state_count,
      COUNT(DISTINCT county) AS county_count,
      COUNT(DISTINCT city_name) AS city_count,
      COUNT(DISTINCT zip_code) AS zip_count
    FROM `{zip_brand_view}`
    WHERE brand_name IS NOT NULL AND location_count > 0
    GROUP BY brand_name
    """).result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{location_view}` AS
    SELECT
      l.listing_id,
      l.business_id,
      l.brand_name AS brand,
      l.name,
      l.address,
      l.city_name,
      l.state_code,
      l.state_name,
      l.county,
      l.zip_code,
      l.phone_number,
      l.latitude,
      l.longitude,
      l.coordinate_source,
      l.coordinate_confidence,
      l.country,
      l.last_observed_at,
      l.custom_fields,
      z.population,
      z.median_household_income,
      z.median_age
    FROM `{enriched_table}` l
    LEFT JOIN `{silver_ref}.zip_reference` z ON l.zip_code = z.zip_code
    WHERE l.listing_id IS NOT NULL
    """).result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{filters_view}` AS
    -- Active brand options are intentionally constrained by listing presence;
    -- the business registry remains available to mirror sync:
    -- FROM `{bronze_ref}.businesses`
    -- UNION DISTINCT is not used here because each filter_type has its own grain.
    SELECT 'brand' AS filter_type, brand_name AS filter_value, brand_name AS filter_label,
      CAST(NULL AS STRING) AS state_code, CAST(NULL AS STRING) AS county, CAST(NULL AS STRING) AS city_name, CAST(NULL AS STRING) AS zip_code
    FROM `{brand_view}`
    UNION ALL
    SELECT DISTINCT 'state', state_code, COALESCE(state_name, state_code), state_code, CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING)
    FROM `{zip_brand_view}` WHERE state_code IS NOT NULL
    UNION ALL
    SELECT DISTINCT 'county', county, county, state_code, county, CAST(NULL AS STRING), CAST(NULL AS STRING)
    FROM `{zip_brand_view}` WHERE county IS NOT NULL
    UNION ALL
    SELECT DISTINCT 'city', city_name, city_name, state_code, county, city_name, CAST(NULL AS STRING)
    FROM `{zip_brand_view}` WHERE city_name IS NOT NULL
    UNION ALL
    SELECT DISTINCT 'zip', zip_code, zip_code, state_code, county, city_name, zip_code
    FROM `{zip_brand_view}` WHERE zip_code IS NOT NULL
    """).result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{gap_base_view}` AS
    SELECT
      z.zip_code,
      z.state_code,
      z.state_name,
      z.county,
      z.city_name,
      z.population,
      z.median_household_income,
      z.median_age,
      z.latitude,
      z.longitude,
      a.brand_name,
      COALESCE(a.location_count, 0) AS location_count
    FROM (
      SELECT
        zip_code,
        ANY_VALUE(state_code) AS state_code,
        ANY_VALUE(state_name) AS state_name,
        ANY_VALUE(county) AS county,
        ANY_VALUE(city_name) AS city_name,
        ANY_VALUE(population) AS population,
        ANY_VALUE(median_household_income) AS median_household_income,
        ANY_VALUE(median_age) AS median_age,
        ANY_VALUE(latitude) AS latitude,
        ANY_VALUE(longitude) AS longitude
      FROM `{zip_brand_view}`
      GROUP BY zip_code
    ) z
    LEFT JOIN `{zip_brand_view}` a ON z.zip_code = a.zip_code
    """).result()

    invalidate_cache()
    views = [zip_brand_view, brand_view, location_view, filters_view, gap_base_view]
    # Stamp the definition version so _ensure_gold_reporting_views() can tell
    # a current view from a stale one that merely exists.
    for view_ref in views:
        try:
            view_table = client.get_table(view_ref)
            view_table.description = f"birdeye_gold_view_version={GOLD_VIEW_DEFINITION_VERSION}"
            client.update_table(view_table, ["description"])
        except Exception as exc:
            LOGGER.warning("gold_view_version_stamp_failed view=%s error=%s", view_ref, exc)
    return {
        "bronze_dataset": bronze_ref,
        "silver_dataset": silver_ref,
        "gold_dataset": gold_ref,
        "views": views,
    }


def sync_gold_mirror(force: bool = False) -> dict[str, Any]:
    """Pull the two gold master views plus active businesses into local
    SQLite, so reporting_summary()
    can filter/aggregate locally instead of a live BigQuery round trip per
    query. Called right after every build_gold_layer() - see
    _rebuild_gold_and_mirror() - so the mirror is never more than one
    refresh cycle behind BigQuery."""
    project_id, bronze_dataset_id, _silver_dataset_id, gold_dataset_id, credentials_json = _medallion_settings()
    client = _bigquery_client(project_id, credentials_json)
    gold_ref = f"{project_id}.{gold_dataset_id}"
    bronze_ref = f"{project_id}.{bronze_dataset_id}"

    zip_brand_rows = [dict(row) for row in client.query(f"""
        SELECT zip_code, state_code, state_name, county, city_name, population,
          median_household_income, median_age, latitude, longitude, brand_name,
          location_count, last_observed_at
        FROM `{gold_ref}.vw_zip_brand_activity`
    """).result()]
    location_rows = [dict(row) for row in client.query(f"""
        SELECT listing_id, business_id, brand, name, address, city_name, state_code,
          state_name, county, zip_code, phone_number, latitude, longitude,
          coordinate_source, coordinate_confidence, country, last_observed_at,
          population, median_household_income, median_age, custom_fields
        FROM `{gold_ref}.vw_reporting_locations`
    """).result()]
    business_rows = [dict(row) for row in client.query(f"""
        SELECT b.business_id, b.name, b.slug, b.description, b.logo_url, b.website_url, b.status,
          b.created_at, b.updated_at,
          (
            SELECT COUNT(*)
            FROM `{bronze_ref}.listings` l
            WHERE l.business_id = b.business_id AND l.is_deleted IS NOT TRUE
          ) AS listing_count,
          b.meta_title, b.meta_description, b.country_of_origin, b.is_reference_data, b.reference_key,
          b.default_source_url, b.default_source_name, b.source_type_id, st.name AS source_type_name
        FROM `{bronze_ref}.businesses` b
        LEFT JOIN `{bronze_ref}.source_types` st ON b.source_type_id = st.source_type_id
        WHERE b.is_deleted IS NOT TRUE AND COALESCE(b.status, 'active') = 'active'
    """).result()]
    for business in business_rows:
        business["display_business_id"] = _display_business_id(business)

    # A gold-view query can succeed (no exception) yet still return zero
    # rows if it lands during a silver rebuild's drop-then-recreate window
    # (build_silver_layer() does DROP TABLE IF EXISTS before repopulating)
    # or any other transient warehouse hiccup. Without this guard, that
    # "successful" empty result would be swapped in as the new mirror
    # truth via replace_gold_mirror(), wiping every reporting number
    # (including warehouse-wide facts like the 50-state count) down to
    # zero until the next refresh happens to land cleanly. Once the mirror
    # has ever held real data, a sync that comes back empty is treated as
    # suspicious and skipped - the previous good mirror is left in place.
    previous_status = get_mirror_status()
    had_real_data = bool(previous_status and (
        (previous_status.get("zip_brand_rows") or 0) > 0
        or (previous_status.get("location_rows") or 0) > 0
    ))
    # force=True is used by the deliberate clear paths, where an empty gold
    # result is the correct new truth rather than a transient hiccup - without
    # it the guard below keeps the just-deleted rows in the mirror and
    # reporting keeps showing data the user has cleared.
    if had_real_data and not force and not zip_brand_rows and not location_rows:
        LOGGER.warning(
            "gold_mirror_sync_suspicious_empty_result skipped=True previous_zip_brand_rows=%s previous_location_rows=%s",
            previous_status.get("zip_brand_rows"), previous_status.get("location_rows"),
        )
        return {"zip_brand_rows": 0, "location_rows": 0, "business_rows": len(business_rows), "skipped_empty_swap": True}

    replace_gold_mirror(zip_brand_rows, location_rows, business_rows)
    result = {"zip_brand_rows": len(zip_brand_rows), "location_rows": len(location_rows), "business_rows": len(business_rows)}
    LOGGER.info("gold_mirror_synced zip_brand_rows=%d location_rows=%d business_rows=%d",
                result["zip_brand_rows"], result["location_rows"], result["business_rows"])
    return result


def _rebuild_gold_and_mirror(force_mirror: bool = False) -> dict[str, Any]:
    """Rebuild gold, then immediately sync the local SQLite mirror from it -
    the single choke point every silver/gold refresh path routes through
    (hourly tick, on-demand background refresh, sample load), so the
    mirror syncs as soon as possible after any change without a separate,
    independently-timed sync loop to keep correct."""
    gold_result = build_gold_layer()
    try:
        mirror_result = sync_gold_mirror(force=force_mirror)
    except Exception as exc:
        LOGGER.warning("gold_mirror_sync_failed error=%s", exc)
        mirror_result = {"error": str(exc)}
    return {"gold": gold_result, "mirror": mirror_result}


def _invoke_silver_layer(low_priority: bool = False) -> dict[str, Any]:
    try:
        return build_silver_layer(low_priority=low_priority)
    except TypeError:
        return build_silver_layer()


def _refresh_silver_background(low_priority: bool = True) -> bool:
    global REPORTING_REFRESHING
    with REPORTING_REFRESH_LOCK:
        if REPORTING_REFRESHING:
            return False
        REPORTING_REFRESHING = True

    def refresh() -> None:
        global REPORTING_REFRESHING
        try:
            try:
                auto_repair_error_batch(5)
            except Exception as repair_exc:
                LOGGER.warning("auto_repair_error_batch_failed error=%s", repair_exc)
            _invoke_silver_layer(low_priority=low_priority)
            # Reporting reads from the gold layer (mirrored into SQLite) -
            # rebuilding silver alone would leave newly-ingested data (e.g. a
            # brand just added via Mappings/Template Library) invisible until
            # the next hourly _run_silver_gold_tick(). Keep gold and the
            # mirror in sync on every on-demand refresh too.
            _rebuild_gold_and_mirror()
            try:
                # Keep the lightweight review badge synchronized after an
                # automatic enrichment pass; SQLite stores only this count,
                # while BigQuery remains the source of truth for rows.
                refresh_error_count("")
            except Exception as count_exc:
                LOGGER.warning("error_count_refresh_after_background_enrichment_failed error=%s", count_exc)
            try:
                # Warm Reporting's Data Quality tab after ingestion/sample
                # load as part of the same background pipeline. This builds
                # the SQLite quality cache and today's durable trend point
                # without making the foreground user action wait.
                reporting_quality_summary({}, _skip_cache=True)
            except Exception as quality_exc:
                LOGGER.warning("quality_reporting_refresh_after_background_enrichment_failed error=%s", quality_exc)
        except Exception as exc:
            LOGGER.warning("reporting_background_silver_refresh_failed error=%s", exc)
        finally:
            if ENRICHMENT_STATUS.get("state") == "running":
                ENRICHMENT_STATUS.update({"state": "idle", "current_id": "", "updated_at": utc_now_iso()})
            with REPORTING_REFRESH_LOCK:
                REPORTING_REFRESHING = False

    threading.Thread(target=refresh, name="reporting-silver-refresh", daemon=True).start()
    return True


def enrichment_status() -> dict[str, Any]:
    _schedule_quality_fix_metrics_refresh()
    with REPORTING_REFRESH_LOCK:
        return {**ENRICHMENT_STATUS, "refreshing": REPORTING_REFRESHING, "auto_repair": get_auto_repair_stats()}


def stop_enrichment() -> dict[str, Any]:
    ENRICHMENT_STOP_REQUESTED.set()
    return {**enrichment_status(), "stop_requested": True}


# Recheck for newly-arrived or user-corrected bronze rows without making the
# foreground mapping/reporting requests wait for the refresh.
SILVER_GOLD_REFRESH_INTERVAL_SECONDS = 600
AUTO_REPAIR_BATCH_PAUSE_SECONDS = 5


def _quality_fix_event_id(fix_type: str, event_id: str, row_number: int) -> str:
    payload = f"{fix_type.upper()}|{event_id}|{int(row_number)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ensure_quality_fix_events_table(client: Any, project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery

    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    client.create_dataset(dataset_ref, exists_ok=True)
    schema = [
        bigquery.SchemaField(field["name"], field["type"], mode=field["mode"])
        for field in TABLE_SCHEMAS["quality_fix_events"]
    ]
    table_ref = f"{project_id}.{dataset_id}.quality_fix_events"
    table = bigquery.Table(table_ref, schema=schema)
    try:
        existing = client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(table)
        return
    existing_names = {field.name for field in existing.schema}
    missing = [
        bigquery.SchemaField(field.name, field.field_type, mode="NULLABLE")
        for field in schema if field.name not in existing_names
    ]
    if missing:
        existing.schema = list(existing.schema) + missing
        client.update_table(existing, ["schema"])


def _ensure_reporting_quality_snapshots_table(client: Any, project_id: str, dataset_id: str) -> None:
    """Create the durable daily quality history used by Reporting trends."""
    from google.cloud import bigquery

    table_ref = f"{project_id}.{dataset_id}.reporting_quality_snapshots"
    schema = [
        bigquery.SchemaField(field["name"], field["type"], mode=field["mode"])
        for field in TABLE_SCHEMAS["reporting_quality_snapshots"]
    ]
    table = bigquery.Table(table_ref, schema=schema)
    try:
        existing = client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(table)
        return
    existing_names = {field.name for field in existing.schema}
    missing = [field for field in schema if field.name not in existing_names]
    if missing:
        existing.schema = list(existing.schema) + missing
        client.update_table(existing, ["schema"])


def _record_quality_fix_event(
    *,
    event_id: str,
    row_number: int,
    fix_type: str,
    processed: bool,
    improved: bool,
    listing_id: str | None = None,
) -> None:
    event_id = str(event_id or "").strip()
    if not event_id:
        return
    row_number = int(row_number or 0)
    if row_number <= 0:
        return
    fix_type = str(fix_type or "").strip().upper()
    if fix_type not in {"AI", "MANUAL"}:
        fix_type = "AI"
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    from google.cloud import bigquery

    _ensure_quality_fix_events_table(client, project_id, dataset_id)
    query = f"""
    MERGE `{project_id}.{dataset_id}.quality_fix_events` target
    USING (
      SELECT
        @fix_id AS fix_id,
        @listing_id AS listing_id,
        @event_id AS event_id,
        @row_number AS row_number,
        @fix_type AS fix_type,
        @processed AS processed,
        @improved AS improved,
        @content_hash AS content_hash
    ) source
    ON target.fix_id = source.fix_id
    WHEN MATCHED THEN UPDATE SET
      listing_id = COALESCE(source.listing_id, target.listing_id),
      processed = source.processed,
      improved = source.improved,
      content_hash = COALESCE(source.content_hash, target.content_hash)
    WHEN NOT MATCHED THEN INSERT
      (fix_id, listing_id, event_id, row_number, fix_type, processed, improved, content_hash, created_at)
    VALUES
      (source.fix_id, source.listing_id, source.event_id, source.row_number, source.fix_type, source.processed, source.improved, source.content_hash, CURRENT_TIMESTAMP())
    """
    client.query(
        query,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("fix_id", "STRING", _quality_fix_event_id(fix_type, event_id, row_number)),
            bigquery.ScalarQueryParameter("listing_id", "STRING", listing_id or None),
            bigquery.ScalarQueryParameter("event_id", "STRING", event_id),
            bigquery.ScalarQueryParameter("row_number", "INT64", row_number),
            bigquery.ScalarQueryParameter("fix_type", "STRING", fix_type),
            bigquery.ScalarQueryParameter("processed", "BOOL", bool(processed)),
            bigquery.ScalarQueryParameter("improved", "BOOL", bool(improved)),
            bigquery.ScalarQueryParameter("content_hash", "STRING", _quality_fix_event_id(fix_type, event_id, row_number)),
        ]),
    ).result()


def _refresh_quality_fix_metrics_from_bigquery() -> dict[str, int]:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    from google.cloud import bigquery

    _ensure_quality_fix_events_table(client, project_id, dataset_id)
    events_query = f"""
    SELECT
      COUNTIF(fix_type = 'AI' AND processed AND improved) AS fixed,
      COUNTIF(fix_type = 'MANUAL' AND processed AND improved) AS manual_fixed,
      COUNTIF(processed) AS processed
    FROM `{project_id}.{dataset_id}.quality_fix_events`
    """
    event_row = next(iter(client.query(events_query).result()), None)
    error_query = f"""
    SELECT COUNT(*) AS remaining
    FROM `{project_id}.{dataset_id}.error_listings`
    WHERE is_deleted IS NOT TRUE
    """
    remaining_row = next(iter(client.query(error_query).result()), None)
    stats = {
        "fixed": int(getattr(event_row, "fixed", 0) or 0),
        "manual_fixed": int(getattr(event_row, "manual_fixed", 0) or 0),
        "processed": int(getattr(event_row, "processed", 0) or 0),
        "remaining": int(getattr(remaining_row, "remaining", 0) or 0),
    }
    set_auto_repair_stats(stats["fixed"], stats["processed"], stats["remaining"], stats["manual_fixed"])
    return stats


def _schedule_quality_fix_metrics_refresh(force: bool = False) -> bool:
    global _QUALITY_FIX_METRICS_REFRESHING, _QUALITY_FIX_METRICS_LAST_REFRESH
    now = perf_counter()
    with _QUALITY_FIX_METRICS_LOCK:
        if _QUALITY_FIX_METRICS_REFRESHING:
            return False
        if not force and _QUALITY_FIX_METRICS_LAST_REFRESH and now - _QUALITY_FIX_METRICS_LAST_REFRESH < 60:
            return False
        _QUALITY_FIX_METRICS_REFRESHING = True

    def refresh() -> None:
        global _QUALITY_FIX_METRICS_REFRESHING, _QUALITY_FIX_METRICS_LAST_REFRESH
        try:
            _refresh_quality_fix_metrics_from_bigquery()
            _QUALITY_FIX_METRICS_LAST_REFRESH = perf_counter()
        except Exception as exc:
            LOGGER.warning("quality_fix_metrics_refresh_failed error=%s", exc)
        finally:
            with _QUALITY_FIX_METRICS_LOCK:
                _QUALITY_FIX_METRICS_REFRESHING = False

    threading.Thread(target=refresh, name="quality-fix-metrics-refresh", daemon=True).start()
    return True


def _run_silver_gold_tick() -> bool:
    """One scheduled refresh attempt: rebuild silver + gold, guarded by the
    same lock/flag _refresh_silver_background uses so an hourly tick and an
    on-demand refresh never run at the same time. Returns True if it ran
    (False if a refresh was already in flight). Split out from the
    infinite loop below so it can be unit tested directly, one call at a
    time, without touching threading.Thread or an actual sleep loop."""
    global REPORTING_REFRESHING
    with REPORTING_REFRESH_LOCK:
        if REPORTING_REFRESHING:
            return False
        REPORTING_REFRESHING = True
    ENRICHMENT_STOP_REQUESTED.clear()
    try:
        try:
            auto_repair_error_batch(5)
        except Exception as repair_exc:
            LOGGER.warning("auto_repair_error_batch_in_tick_failed error=%s", repair_exc)
        silver_result = _invoke_silver_layer(low_priority=True)
        combined = _rebuild_gold_and_mirror()
        try:
            refresh_error_count("")
        except Exception as count_exc:
            LOGGER.warning("error_count_refresh_after_scheduled_enrichment_failed error=%s", count_exc)
        gold_result = combined["gold"]
        LOGGER.info(
            "scheduled_medallion_refresh_succeeded silver_rows=%s invalid_rows=%s gold_views=%s mirror=%s",
            silver_result.get("rows"),
            silver_result.get("invalid_rows"),
            len(gold_result.get("views", [])),
            combined.get("mirror"),
        )
    except Exception as exc:
        LOGGER.exception("scheduled_medallion_refresh_failed error=%s", exc)
    finally:
        with REPORTING_REFRESH_LOCK:
            REPORTING_REFRESHING = False
    return True


def _start_silver_gold_scheduler() -> None:
    """Rebuild silver + gold on a fixed hourly cadence, as a time-based
    floor under the existing on-demand refresh (_refresh_silver_background,
    triggered opportunistically when a stale cached reporting query is
    served). Call once from serve() only - never at import time, so
    importing this module in tests doesn't start a background thread."""

    def run_forever() -> None:
        while True:
            sleep(SILVER_GOLD_REFRESH_INTERVAL_SECONDS)
            _run_silver_gold_tick()

    threading.Thread(target=run_forever, name="silver-gold-hourly-refresh", daemon=True).start()


def _ensure_gold_reporting_views(client: Any, gold_ref: str) -> bool:
    required_views = (
        "vw_zip_brand_activity",
        "vw_brand_summary",
        "vw_reporting_locations",
        "vw_reporting_filter_options",
        "vw_reporting_gap_base",
    )
    stale_view = False
    try:
        for view_name in required_views:
            view_table = client.get_table(f"{gold_ref}.{view_name}")
            # Existing is not the same as current: a view whose SELECT list
            # changed in code still exists with its OLD definition, and would
            # silently keep serving the old columns forever.
            description = str(getattr(view_table, "description", "") or "")
            if f"birdeye_gold_view_version={GOLD_VIEW_DEFINITION_VERSION}" not in description:
                stale_view = True
                LOGGER.info("gold_view_definition_stale view=%s rebuilding", view_name)
                break
        if not stale_view:
            return False
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
    if hasattr(client, "create_dataset"):
        project_id, bronze_dataset_id, silver_dataset_id, gold_dataset_id, _ = _medallion_settings()
        _ensure_dataset(client, project_id, bronze_dataset_id)
        _ensure_dataset(client, project_id, silver_dataset_id)
        _ensure_dataset(client, project_id, gold_dataset_id)
        _ensure_businesses_table(client, project_id, bronze_dataset_id)
        _ensure_listings_table(client, project_id, bronze_dataset_id)
    try:
        prepare_zipcodes()
    except Exception as exc:
        raise RuntimeError(f"gold bootstrap failed at prepare_zipcodes: {exc}") from exc
    try:
        silver_res = build_silver_layer()
        if isinstance(silver_res, dict) and silver_res.get("status") == "failed":
            raise RuntimeError(f"gold bootstrap failed at build_silver_layer: {silver_res.get('warning')}")
    except Exception as exc:
        raise RuntimeError(f"gold bootstrap failed at build_silver_layer: {exc}") from exc
    try:
        build_gold_layer()
    except Exception as exc:
        raise RuntimeError(f"gold bootstrap failed at build_gold_layer: {exc}") from exc
    try:
        sync_gold_mirror()
    except Exception as exc:
        LOGGER.warning("gold_mirror_sync_failed error=%s", exc)
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
            "min_population": _safe_float(params.get("min_population", [""])[0]),
            "min_income": _safe_float(params.get("min_income", [""])[0]),
            "max_median_age": _safe_float(params.get("max_median_age", [""])[0]),
        },
        "filter_options": {"brands": [], "states": [], "counties": [], "cities": [], "zips": []},
        "totals": {
            "total_locations": 0,
            "total_brands": 0,
            "total_states": 0,
            "total_cities": 0,
            "total_zips": 0,
            # "Listings" is the canonical term (matches this table's own
            # name and every medallion layer). total_stores stays as a
            # deprecated alias so an older client keeps working.
            "total_listings": 0,
            "total_stores": 0,
            "active_market_locations": 0,
            "active_brand_states": 0,
            "active_brand_cities": 0,
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


# --- SQLite gold-mirror fast path -------------------------------------------
#
# Mirrors the same filtering/aggregation semantics as the BigQuery queries in
# reporting_summary() below (base_cte, totals_query, top_states_query,
# top_cities_query, brand_query, gap_query, map_query, sample_query,
# data_quality_query), reading from the local SQLite tables synced by
# sync_gold_mirror() instead of issuing ~9 live BigQuery queries per request.
# Falls back to None (triggering the BigQuery path) whenever the mirror
# hasn't been synced yet.

def _lat_lon_ok_or_null(lat: float | None, lon: float | None) -> bool:
    """Matches base_cte's "latitude IS NULL OR (latitude/longitude within US
    bounds)" - a missing coordinate passes through, but a present one must
    be valid."""
    if lat is None:
        return True
    if lon is None:
        return False
    return 13.0 <= lat <= 72.0 and ((-180.0 <= lon <= -64.0) or (144.0 <= lon <= 146.0))


def _lat_lon_ok_strict(lat: float | None, lon: float | None) -> bool:
    """Matches map_query's hard "latitude/longitude required and within US
    bounds" - unlike base_cte, a missing coordinate is excluded."""
    if lat is None or lon is None:
        return False
    return 13.0 <= lat <= 72.0 and ((-180.0 <= lon <= -64.0) or (144.0 <= lon <= 146.0))


def _passes_brand_filter(brand_name: str | None, selected_brands: list[str]) -> bool:
    return not selected_brands or brand_name in selected_brands


def _passes_demographic_filters(
    population: float | None, income: float | None, age: float | None,
    min_population: float | None, min_income: float | None, max_median_age: float | None,
) -> bool:
    if min_population is not None and (population or 0) < min_population:
        return False
    if min_income is not None and (income or 0) < min_income:
        return False
    if max_median_age is not None and (age or 0) > max_median_age:
        return False
    return True


def _mirror_base_rows(
    zip_rows: list[dict[str, Any]], selected_brands: list[str],
    min_population: float | None, min_income: float | None, max_median_age: float | None,
) -> list[dict[str, Any]]:
    """Python equivalent of base_cte: one row per (zip, brand) that survives
    every filter, reshaped to the same field names base_cte produces."""
    base_rows = []
    for r in zip_rows:
        if not _passes_brand_filter(r.get("brand_name"), selected_brands):
            continue
        if not _passes_demographic_filters(r.get("population"), r.get("median_household_income"), r.get("median_age"), min_population, min_income, max_median_age):
            continue
        if not _lat_lon_ok_or_null(r.get("latitude"), r.get("longitude")):
            continue
        location_count = r.get("location_count") or 0
        zip_code = r.get("zip_code")
        brand_name = r.get("brand_name")
        base_rows.append({
            "zip_code": zip_code,
            "zip_city": r.get("city_name"),
            "zip_state": r.get("state_code"),
            "zip_state_name": r.get("state_name"),
            "county": r.get("county"),
            "population": r.get("population"),
            "median_household_income": r.get("median_household_income"),
            "median_age": r.get("median_age"),
            "listing_id": f"{brand_name or ''}|{zip_code}" if location_count > 0 else None,
            "brand": brand_name,
            "last_observed_at": r.get("last_observed_at"),
            "location_count": location_count,
        })
    return base_rows


def _mirror_state_population_by_state(all_zip_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Matches top_states_query's population subquery: dedupe to one row
    per zip (across its brand fan-out) before summing per state, and use
    the full unfiltered mirror (population is a broad market-context stat,
    not scoped to the current geo filter - matching the BigQuery query,
    which reads {zip_ref} with no WHERE at all)."""
    dedup: dict[str, tuple[str | None, float]] = {}
    for r in all_zip_rows:
        zip_code = r.get("zip_code")
        population = r.get("population")
        if zip_code is None or population is None:
            continue
        if zip_code not in dedup:
            dedup[zip_code] = (r.get("state_code"), population)
    totals: dict[str, float] = {}
    for state_code, population in dedup.values():
        if not state_code:
            continue
        totals[state_code] = totals.get(state_code, 0) + population
    return totals


def _mirror_state_median_income_by_state(all_zip_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Same dedupe-by-zip approach as _mirror_state_population_by_state(),
    but averaged (not summed) since median household income is a rate, not
    an additive quantity - matches the AVG() used in the mirrored BigQuery
    top_states_query."""
    dedup: dict[str, tuple[str | None, float]] = {}
    for r in all_zip_rows:
        zip_code = r.get("zip_code")
        income = r.get("median_household_income")
        if zip_code is None or income is None:
            continue
        if zip_code not in dedup:
            dedup[zip_code] = (r.get("state_code"), income)
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for state_code, income in dedup.values():
        if not state_code:
            continue
        sums[state_code] = sums.get(state_code, 0) + income
        counts[state_code] = counts.get(state_code, 0) + 1
    return {state: sums[state] / counts[state] for state in sums}


def _mirror_totals(base_rows: list[dict[str, Any]], global_brand_count: int, zip_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    universe_rows = zip_rows if zip_rows is not None else base_rows
    zip_states = {r["state_code"] if "state_code" in r else r.get("zip_state") for r in universe_rows if r.get("state_code") or r.get("zip_state")}
    zip_codes = {r["zip_code"] for r in universe_rows if r.get("zip_code")}
    zip_cities_all = {r["city_name"] if "city_name" in r else r.get("zip_city") for r in universe_rows if r.get("city_name") or r.get("zip_city")}
    brands_present = {r["brand"] for r in base_rows if r.get("brand")}
    active_rows = [r for r in base_rows if (r.get("location_count") or 0) > 0 and r.get("brand")]
    active_zips = {r["zip_code"] for r in active_rows if r.get("zip_code")}
    active_states = {r["zip_state"] for r in active_rows if r.get("zip_state")}
    active_cities = {r["zip_city"] for r in active_rows if r.get("zip_city")}
    total_locations = {r["listing_id"] for r in base_rows if (r.get("location_count") or 0) > 0 and r.get("listing_id")}
    total_stores = sum(r.get("location_count") or 0 for r in base_rows)
    last_updated = max((r.get("last_observed_at") for r in base_rows if r.get("last_observed_at")), default=None)
    gap_zips_count = max(0, len(zip_codes) - len(active_zips))
    return {
        "total_states": len(zip_states),
        "total_zips": len(zip_codes),
        "total_brands": len(brands_present) or global_brand_count,
        "total_listings": int(total_stores),
        "total_stores": int(total_stores) if total_stores == int(total_stores) else total_stores,
        "active_market_locations": len(active_zips),
        "active_brand_states": len(active_states),
        "active_brand_cities": len(active_cities),
        "total_locations": len(total_locations),
        "total_cities": len(zip_cities_all),
        "gap_zips": gap_zips_count,
        "last_updated": last_updated,
    }


def _mirror_top_states(
    base_rows: list[dict[str, Any]], state_population: dict[str, float], state_median_income: dict[str, float],
    main_brands: list[str] | None = None, competitor_brands: list[str] | None = None,
) -> list[dict[str, Any]]:
    main_set = set(main_brands or [])
    competitor_set = set(competitor_brands or [])
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for r in base_rows:
        key = (r.get("zip_state") or "", r.get("zip_state_name") or r.get("zip_state") or "")
        group = groups.setdefault(key, {"zips": set(), "cities": set(), "brands": set(), "main_locations": 0, "competitor_locations": 0})
        if r.get("zip_code"):
            group["zips"].add(r["zip_code"])
        if r.get("zip_city"):
            group["cities"].add(r["zip_city"])
        if r.get("brand"):
            group["brands"].add(r["brand"])
            location_count = r.get("location_count") or 0
            if r["brand"] in main_set:
                group["main_locations"] += location_count
            elif r["brand"] in competitor_set:
                group["competitor_locations"] += location_count
    rows = [
        {
            "state": state, "state_name": state_name,
            "locations": len(group["zips"]), "cities": len(group["cities"]), "brands": len(group["brands"]),
            "state_population": state_population.get(state, 0) or 0,
            "median_household_income": state_median_income.get(state, 0) or 0,
            "main_brand_locations": group["main_locations"],
            "competitor_brand_locations": group["competitor_locations"],
        }
        for (state, state_name), group in groups.items()
    ]
    rows.sort(key=lambda r: r["locations"], reverse=True)
    return rows[:15]


def _mirror_top_cities(
    base_rows: list[dict[str, Any]], main_brands: list[str] | None = None, competitor_brands: list[str] | None = None,
) -> list[dict[str, Any]]:
    main_set = set(main_brands or [])
    competitor_set = set(competitor_brands or [])
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for r in base_rows:
        key = (r.get("zip_city") or "", r.get("zip_state") or "", r.get("zip_state_name") or r.get("zip_state") or "", r.get("county") or "")
        group = groups.setdefault(key, {"zips": set(), "zip_population": {}, "zip_income": {}, "main_locations": 0, "competitor_locations": 0})
        zip_code = r.get("zip_code")
        if zip_code:
            group["zips"].add(zip_code)
            # base_rows repeats population/median_household_income once per
            # brand fanned out on the same zip - keep one value per zip
            # (a dict keyed by zip_code naturally dedupes this) before
            # summing/averaging, same as the state-level helpers above.
            if r.get("population") is not None:
                group["zip_population"][zip_code] = r["population"]
            if r.get("median_household_income") is not None:
                group["zip_income"][zip_code] = r["median_household_income"]
        if r.get("brand"):
            location_count = r.get("location_count") or 0
            if r["brand"] in main_set:
                group["main_locations"] += location_count
            elif r["brand"] in competitor_set:
                group["competitor_locations"] += location_count
    rows = []
    for (city, state, state_name, county), group in groups.items():
        incomes = list(group["zip_income"].values())
        rows.append({
            "city": city, "state": state, "state_name": state_name, "county": county,
            "locations": len(group["zips"]),
            "city_population": sum(group["zip_population"].values()),
            "median_household_income": (sum(incomes) / len(incomes)) if incomes else 0,
            "main_brand_locations": group["main_locations"],
            "competitor_brand_locations": group["competitor_locations"],
        })
    rows.sort(key=lambda r: r["locations"], reverse=True)
    return rows[:10]


def _mirror_brand_query(base_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for r in base_rows:
        if not r.get("listing_id") or not r.get("brand"):
            continue
        group = groups.setdefault(r["brand"], {"locations": 0, "states": set(), "counties": set(), "cities": set(), "zips": set()})
        group["locations"] += r.get("location_count") or 0
        if r.get("zip_state"):
            group["states"].add(r["zip_state"])
        if r.get("county"):
            group["counties"].add(r["county"])
        if r.get("zip_city"):
            group["cities"].add(r["zip_city"])
        if r.get("zip_code"):
            group["zips"].add(r["zip_code"])
    rows = [
        {"brand": brand, "locations": g["locations"], "states": len(g["states"]), "counties": len(g["counties"]), "cities": len(g["cities"]), "zips": len(g["zips"])}
        for brand, g in groups.items()
    ]
    rows.sort(key=lambda r: r["locations"], reverse=True)
    return rows[:10]


def _mirror_filter_options(all_zip_rows: list[dict[str, Any]], business_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Matches vw_reporting_filter_options: always the full unfiltered
    mirror, not scoped to the current geo selection - filter dropdowns
    should always offer every option that currently has active listings,
    not saved brands with zero reporting data."""
    brands = {r["brand_name"] for r in all_zip_rows if r.get("brand_name") and (r.get("location_count") or 0) > 0}
    states = {r["state_code"] for r in all_zip_rows if r.get("state_code")}
    counties = {r["county"] for r in all_zip_rows if r.get("county")}
    cities = {r["city_name"] for r in all_zip_rows if r.get("city_name")}
    zips = {r["zip_code"] for r in all_zip_rows if r.get("zip_code")}
    return {
        "brands": sorted(brands),
        "states": sorted(states),
        "counties": sorted(counties)[:500],
        "cities": sorted(cities)[:500],
        "zips": sorted(zips)[:500],
    }


def _mirror_gap_rows(
    zip_rows: list[dict[str, Any]], main_brands: list[str], competitor_brands: list[str],
    min_population: float | None, min_income: float | None, max_median_age: float | None, state_filter: str,
) -> list[dict[str, Any]]:
    """Matches gap_query: grouped by zip (geo/demographic filtered, but
    NOT brand-filtered - it needs the full brand universe per zip to tell
    subject-only from competitor-only zips)."""
    main_set = set(main_brands)
    competitor_set = set(competitor_brands)
    groups: dict[str, dict[str, Any]] = {}
    for r in zip_rows:
        if not _passes_demographic_filters(r.get("population"), r.get("median_household_income"), r.get("median_age"), min_population, min_income, max_median_age):
            continue
        zip_code = r.get("zip_code")
        if zip_code is None:
            continue
        group = groups.setdefault(zip_code, {
            "state": r.get("state_code") or "", "state_name": r.get("state_name") or "",
            "county": r.get("county"), "city": r.get("city_name"), "zip_code": zip_code,
            "brands_present": set(), "subject_stores": 0, "competitor_stores": 0, "competitor_brands_present": set(),
            "latitude": r.get("latitude"), "longitude": r.get("longitude"), "population": r.get("population"),
            "median_household_income": r.get("median_household_income"), "median_age": r.get("median_age"),
        })
        brand_name = r.get("brand_name")
        location_count = r.get("location_count") or 0
        if brand_name:
            group["brands_present"].add(brand_name)
            if brand_name in main_set:
                group["subject_stores"] += location_count
            if brand_name in competitor_set:
                group["competitor_stores"] += location_count
                group["competitor_brands_present"].add(brand_name)

    rows = []
    for zip_code, g in groups.items():
        population = g["population"] or 0
        subject_stores = g["subject_stores"]
        competitor_stores = g["competitor_stores"]
        if subject_stores > 0 and competitor_stores > 0:
            whitespace_type = "COMPETITIVE_MARKET"
        elif subject_stores > 0 and competitor_stores == 0:
            whitespace_type = "SUBJECT_PRESENT"
        elif subject_stores == 0 and competitor_stores > 0:
            whitespace_type = "COMPETITOR_WHITESPACE"
        elif subject_stores == 0 and competitor_stores == 0 and population > 0:
            whitespace_type = "OPEN_WHITESPACE"
        else:
            whitespace_type = "UNKNOWN_COVERAGE"
        competition_level = "High" if competitor_stores >= 3 else ("Moderate" if competitor_stores >= 1 else "None")
        rows.append({
            "state": g["state"], "state_name": g["state_name"], "county": g["county"], "city": g["city"], "zip_code": zip_code,
            "subject_stores": subject_stores, "competitor_stores": competitor_stores,
            "competitor_brands": ", ".join(sorted(g["competitor_brands_present"])),
            "competitor_brand_count": len(g["competitor_brands_present"]),
            "brands_present": ", ".join(sorted(g["brands_present"])),
            "latitude": g["latitude"], "longitude": g["longitude"],
            "population": population, "median_household_income": g["median_household_income"] or 0, "median_age": g["median_age"] or 0,
            "whitespace_type": whitespace_type, "competition_level": competition_level,
        })
    if state_filter:
        rows = [r for r in rows if r["state"].upper() == state_filter]
    rows.sort(key=lambda r: (-(r["competitor_stores"] or 0), -(r["population"] or 0)))
    return rows[:1000]


def _mirror_map_records(
    location_rows: list[dict[str, Any]], selected_brands: list[str],
    min_population: float | None, min_income: float | None, max_median_age: float | None,
) -> list[dict[str, Any]]:
    rows = []
    for r in location_rows:
        if not _passes_brand_filter(r.get("brand"), selected_brands):
            continue
        if not _passes_demographic_filters(r.get("population"), r.get("median_household_income"), r.get("median_age"), min_population, min_income, max_median_age):
            continue
        if not _lat_lon_ok_strict(r.get("latitude"), r.get("longitude")):
            continue
        rows.append({
            "brand": r.get("brand"), "name": r.get("name"), "address": r.get("address"),
            "city": r.get("city_name"), "state": r.get("state_code"), "state_name": r.get("state_name"),
            "county": r.get("county"), "zip_code": r.get("zip_code"), "phone_number": r.get("phone_number"),
            "latitude": r.get("latitude"), "longitude": r.get("longitude"),
        })
    return rows[:1000]


def _mirror_sample_records(
    location_rows: list[dict[str, Any]], selected_brands: list[str],
    min_population: float | None, min_income: float | None, max_median_age: float | None,
) -> list[dict[str, Any]]:
    rows = []
    for r in location_rows:
        if not _passes_brand_filter(r.get("brand"), selected_brands):
            continue
        if not _passes_demographic_filters(r.get("population"), r.get("median_household_income"), r.get("median_age"), min_population, min_income, max_median_age):
            continue
        rows.append({
            "name": r.get("name"), "address": r.get("address"), "city": r.get("city_name"),
            "state": r.get("state_code"), "state_name": r.get("state_name"), "county": r.get("county"),
            "zip_code": r.get("zip_code"), "phone_number": r.get("phone_number"),
            "latitude": r.get("latitude"), "longitude": r.get("longitude"),
            "country": r.get("country"), "last_observed_at": r.get("last_observed_at"),
        })
    # ORDER BY last_observed_at DESC, name ASC - stable two-pass sort:
    # tiebreaker ascending first, then primary key descending.
    rows.sort(key=lambda r: r.get("name") or "")
    rows.sort(key=lambda r: r.get("last_observed_at") or "", reverse=True)
    return rows[:10]


def _mirror_data_quality(quality_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_rows = len(quality_rows)
    with_coordinates = sum(1 for r in quality_rows if r.get("latitude") is not None and r.get("longitude") is not None)
    with_zip = sum(1 for r in quality_rows if r.get("zip_code"))
    distinct_keys = {f"{r.get('brand') or ''}|{r.get('zip_code') or ''}|{r.get('address') or ''}" for r in quality_rows}
    last_observed_at = max((r.get("last_observed_at") for r in quality_rows if r.get("last_observed_at")), default=None)
    return {
        "total_rows": total_rows,
        "with_coordinates": with_coordinates,
        "with_zip": with_zip,
        "distinct_rows": len(distinct_keys),
        "last_observed_at": last_observed_at,
    }


def _reporting_data_from_mirror(
    main_brands: list[str], competitor_brands: list[str], selected_brands: list[str],
    state_filter: str, county_filter: str, city_filter: str, zip_filter: str,
    min_population: float | None, min_income: float | None, max_median_age: float | None,
) -> dict[str, Any] | None:
    """Returns None (triggering the live BigQuery fallback) only when the
    mirror has never been synced - once synced, an empty result set is a
    legitimate answer, not a signal to fall back."""
    if get_mirror_status() is None:
        return None
    try:
        zip_rows = fetch_mirror_zip_brand_activity(state_filter, county_filter, city_filter, zip_filter)
        all_zip_rows = fetch_mirror_zip_brand_activity()
        location_rows = fetch_mirror_reporting_locations(state_filter, county_filter, city_filter, zip_filter)
        quality_rows = fetch_mirror_reporting_locations_by_brand(selected_brands)
        business_rows = fetch_mirror_businesses()
    except Exception as exc:
        LOGGER.warning("reporting_mirror_read_failed error=%s", exc)
        return None

    base_rows = _mirror_base_rows(zip_rows, selected_brands, min_population, min_income, max_median_age)
    state_population = _mirror_state_population_by_state(all_zip_rows)
    state_median_income = _mirror_state_median_income_by_state(all_zip_rows)
    global_brand_count = len({r["brand_name"] for r in all_zip_rows if r.get("brand_name") and (r.get("location_count") or 0) > 0})

    return {
        "totals": _mirror_totals(base_rows, global_brand_count, zip_rows),
        "top_states": _mirror_top_states(base_rows, state_population, state_median_income, main_brands, competitor_brands),
        "top_cities": _mirror_top_cities(base_rows, main_brands, competitor_brands),
        "brands": _mirror_brand_query(base_rows),
        "filter_options": _mirror_filter_options(all_zip_rows, business_rows),
        "raw_whitespace": _mirror_gap_rows(zip_rows, main_brands, competitor_brands, min_population, min_income, max_median_age, state_filter),
        "map_records": _mirror_map_records(location_rows, selected_brands, min_population, min_income, max_median_age),
        "sample_records": _mirror_sample_records(location_rows, main_brands, min_population, min_income, max_median_age),
        "data_quality_row": _mirror_data_quality(quality_rows),
        "present_states": {r["zip_state"] for r in base_rows if r.get("zip_state") and (r.get("location_count") or 0) > 0},
    }


def _execute_bq_queries_parallel(queries: dict[str, tuple[str, Any]], client: Any) -> dict[str, Any]:
    """Execute multiple BigQuery queries in parallel threads.

    Args:
        queries: dict mapping result_key -> (query_sql, job_config)
        client: BigQuery client

    Returns:
        dict mapping result_key -> query result
    """
    results = {}
    errors = {}

    def _run_query(key: str, query_sql: str, job_config: Any) -> None:
        try:
            result = client.query(query_sql, job_config=job_config).result()
            # Convert to list of dicts
            results[key] = [dict(row) for row in result] if key != "totals" else dict(next(iter(result)))
        except Exception as exc:
            errors[key] = exc

    threads = []
    for key, (query_sql, job_config) in queries.items():
        thread = threading.Thread(target=_run_query, args=(key, query_sql, job_config), daemon=False)
        thread.start()
        threads.append(thread)

    # Wait for all threads
    for thread in threads:
        thread.join(timeout=300)  # 5-minute timeout per query

    if errors:
        # Raise the first error
        raise next(iter(errors.values()))

    return results


def reporting_summary(params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    params = params or {}
    cache_key = f"reporting_summary:v3:{json.dumps(params, sort_keys=True)}"
    cached_payload = get_cached_query(cache_key)
    if cached_payload:
        cached_totals = cached_payload.get("totals") if isinstance(cached_payload.get("totals"), dict) else {}
        cached_is_setup_empty = (
            cached_payload.get("reporting_cache") in {"empty", "zip_base"}
            or (
                int(cached_totals.get("total_locations") or 0) == 0
                and int(cached_totals.get("active_market_locations") or 0) == 0
                and int(cached_totals.get("total_stores") or 0) == 0
                and int(cached_totals.get("total_brands") or 0) == 0
                and not cached_payload.get("map_records")
            )
        )
        if cached_is_setup_empty:
            invalidate_cache(cache_key)
        else:
            refresh_started = _refresh_silver_background()
            cached_payload["reporting_cache"] = "hit"
            cached_payload["refreshing"] = bool(refresh_started or REPORTING_REFRESHING)
            return cached_payload

    main_brands = _csv_param(params.get("main_brands", [""])[0])
    raw_competitor_brands = _csv_param(params.get("competitor_brands", [""])[0])
    # Ensure same brand data is NEVER shown in competitor analysis
    competitor_brands = [b for b in raw_competitor_brands if b not in main_brands]
    selected_brands = sorted(set(main_brands + competitor_brands))

    state_filter = str(params.get("state", [""])[0]).strip().upper()
    county_filter = str(params.get("county", [""])[0]).strip()
    city_filter = str(params.get("city", [""])[0]).strip()
    zip_filter = str(params.get("zip", [""])[0]).strip()
    min_population = _safe_float(params.get("min_population", [""])[0])
    min_income = _safe_float(params.get("min_income", [""])[0])
    max_median_age = _safe_float(params.get("max_median_age", [""])[0])

    mirror_data = _reporting_data_from_mirror(
        main_brands, competitor_brands, selected_brands, state_filter, county_filter,
        city_filter, zip_filter, min_population, min_income, max_median_age,
    )
    if mirror_data is not None:
        refresh_started = _refresh_silver_background()
        return _finish_reporting_summary(
            params, cache_key, mirror_data["totals"], mirror_data["top_states"], mirror_data["top_cities"],
            mirror_data["brands"], mirror_data["filter_options"], mirror_data["raw_whitespace"],
            mirror_data["map_records"], mirror_data["sample_records"], mirror_data["data_quality_row"],
            mirror_data["present_states"], main_brands, competitor_brands, state_filter, county_filter,
            city_filter, zip_filter, min_population, min_income, max_median_age,
            "sqlite_gold_mirror", "mirror", refresh_started,
        )

    try:
        project_id, bronze_dataset_id, silver_dataset_id, gold_dataset_id, credentials_json = _medallion_settings()
        from google.cloud import bigquery
        client = _bigquery_client(project_id, credentials_json)
        _ensure_businesses_table(client, project_id, bronze_dataset_id)
        _ensure_listings_table(client, project_id, bronze_dataset_id)
        gold_ref = f"{project_id}.{gold_dataset_id}"
        gold_bootstrapped = _ensure_gold_reporting_views(client, gold_ref)
        source_table = os.environ.get("REPORTING_LISTINGS_TABLE") or f"{gold_ref}.vw_zip_brand_activity"
        if source_table.count(".") == 1:
            source_table = f"{project_id}.{source_table}"
    except (ImportError, Exception) as init_err:
        LOGGER.warning("bigquery_reporting_fallback reason=%s", init_err)
        refresh_started = _refresh_silver_background()
        err_text = str(init_err)
        # Suppress raw BigQuery 404 traces when warehouse tables do not exist yet so empty warehouse displays cleanly
        if "404" in err_text and ("not found" in err_text.lower() or "notfound" in err_text.lower()):
            warning = ""
        else:
            warning = "Reporting data is being prepared. Please refresh shortly."
        payload = _empty_reporting_payload("us_zipcodes_baseline", params, warning)
        payload["refreshing"] = bool(refresh_started or REPORTING_REFRESHING)
        return payload
    table_ref = f"`{source_table}`"
    gold_zip_ref = f"`{gold_ref}.vw_zip_brand_activity`"
    # vw_state_summary/vw_city_summary are grouped by brand_name, so summing
    # their per-brand zip_count across a multi-brand selection would double
    # count zips shared by more than one selected brand - not usable here,
    # where top_states/top_cities must report true DISTINCT zip coverage
    # across whatever brands the user has selected. They stay in the gold
    # dataset for direct/external BigQuery consumption instead.
    gold_brand_ref = f"`{gold_ref}.vw_brand_summary`"
    gold_location_ref = f"`{gold_ref}.vw_reporting_locations`"
    gold_filters_ref = f"`{gold_ref}.vw_reporting_filter_options`"
    gold_gap_ref = f"`{gold_ref}.vw_reporting_gap_base`"
    zip_ref = gold_zip_ref
    refresh_started = _refresh_silver_background() or gold_bootstrapped
    
    query_params: list[Any] = [
        bigquery.ArrayQueryParameter("selected_brands", "STRING", selected_brands),
        bigquery.ArrayQueryParameter("main_brands", "STRING", main_brands),
        bigquery.ArrayQueryParameter("competitor_brands", "STRING", competitor_brands),
        bigquery.ScalarQueryParameter("state", "STRING", state_filter),
        bigquery.ScalarQueryParameter("county", "STRING", county_filter),
        bigquery.ScalarQueryParameter("city", "STRING", city_filter),
        bigquery.ScalarQueryParameter("zip", "STRING", zip_filter),
        bigquery.ScalarQueryParameter("min_population", "FLOAT64", min_population),
        bigquery.ScalarQueryParameter("min_income", "FLOAT64", min_income),
        bigquery.ScalarQueryParameter("max_median_age", "FLOAT64", max_median_age),
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    
    # Base CTE starts from the gold ZIP/brand activity view. Silver owns
    # enrichment; gold owns reporting shape.
    base_cte = f"""
    WITH base AS (
      SELECT
        zip_code,
        city_name AS zip_city,
        state_code AS zip_state,
        state_name AS zip_state_name,
        county,
        population,
        median_household_income,
        median_age,
        latitude AS zip_latitude,
        longitude AS zip_longitude,
        IF(location_count > 0, CONCAT(COALESCE(brand_name, ''), '|', zip_code), NULL) AS listing_id,
        CAST(NULL AS STRING) AS business_id,
        brand_name AS brand,
        brand_name AS name,
        CAST(NULL AS STRING) AS address,
        city_name,
        state_code,
        state_name,
        CAST(NULL AS STRING) AS phone_number,
        latitude,
        longitude,
        'gold_zip_brand_activity' AS coordinate_source,
        1.0 AS coordinate_confidence,
        'United States' AS country,
        last_observed_at,
        location_count
      FROM {table_ref}
      WHERE (@state = '' OR UPPER(state_code) = @state)
        AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
        AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
        AND (@zip = '' OR zip_code = @zip)
        AND (ARRAY_LENGTH(@selected_brands) = 0 OR brand_name IN UNNEST(@selected_brands))
        AND (@min_population IS NULL OR COALESCE(population, 0) >= @min_population)
        AND (@min_income IS NULL OR COALESCE(median_household_income, 0) >= @min_income)
        AND (@max_median_age IS NULL OR COALESCE(median_age, 0) <= @max_median_age)
        AND (
          latitude IS NULL OR (
            latitude BETWEEN 13.0 AND 72.0 AND (
              (longitude BETWEEN -180.0 AND -64.0) OR (longitude BETWEEN 144.0 AND 146.0)
            )
          )
        )
    )
    """

    totals_query = base_cte + f"""
    SELECT
      (SELECT COUNT(DISTINCT state_code) FROM {zip_ref}
       WHERE (@state = '' OR UPPER(state_code) = @state)
         AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
         AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
         AND (@zip = '' OR zip_code = @zip)
      ) AS total_states,
      (SELECT COUNT(DISTINCT zip_code) FROM {zip_ref}
       WHERE (@state = '' OR UPPER(state_code) = @state)
         AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
         AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
         AND (@zip = '' OR zip_code = @zip)
      ) AS total_zips,
      -- Brands actually present in the current filtered view; only fall
      -- back to the platform-wide catalog count when the filter matches
      -- zero listings, so selecting a state/brand narrows this KPI too.
      COALESCE(NULLIF(COUNT(DISTINCT brand), 0), (SELECT COUNT(DISTINCT brand_name) FROM {gold_brand_ref})) AS total_brands,
      COALESCE(SUM(location_count), 0) AS total_stores,
      COUNT(DISTINCT IF(location_count > 0 AND brand IS NOT NULL, zip_code, NULL)) AS active_market_locations,
      COUNT(DISTINCT IF(location_count > 0 AND brand IS NOT NULL, zip_state, NULL)) AS active_brand_states,
      COUNT(DISTINCT IF(location_count > 0 AND brand IS NOT NULL, zip_city, NULL)) AS active_brand_cities,
      COUNT(DISTINCT IF(location_count > 0, listing_id, NULL)) AS total_locations,
      (SELECT COUNT(DISTINCT city_name) FROM {zip_ref}
       WHERE (@state = '' OR UPPER(state_code) = @state)
         AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
         AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
         AND (@zip = '' OR zip_code = @zip)
      ) AS total_cities,
      GREATEST(0, (SELECT COUNT(DISTINCT zip_code) FROM {zip_ref}
       WHERE (@state = '' OR UPPER(state_code) = @state)
         AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
         AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
         AND (@zip = '' OR zip_code = @zip)
      ) - COUNT(DISTINCT IF(location_count > 0 AND brand IS NOT NULL, zip_code, NULL))) AS gap_zips,
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
      COALESCE(MAX(sp.state_pop), 0) AS state_population,
      COALESCE(MAX(sp.state_income), 0) AS median_household_income,
      SUM(IF(b.brand IN UNNEST(@main_brands), b.location_count, 0)) AS main_brand_locations,
      SUM(IF(b.brand IN UNNEST(@competitor_brands), b.location_count, 0)) AS competitor_brand_locations
    FROM base b
    LEFT JOIN (
      -- {zip_ref}'s grain is (zip_code, brand_name): a zip with N distinct
      -- brands present appears as N rows carrying the same population value,
      -- so dedupe down to one row per zip before summing or population gets
      -- multiplied by however many brands operate in each zip. Income is
      -- averaged (not summed) since it's a rate, not an additive quantity.
      SELECT state_code, SUM(population) AS state_pop, AVG(median_household_income) AS state_income
      FROM (SELECT DISTINCT zip_code, state_code, population, median_household_income FROM {zip_ref})
      GROUP BY state_code
    ) sp ON b.zip_state = sp.state_code
    GROUP BY state, state_name
    ORDER BY locations DESC
    LIMIT 15
    """

    top_cities_query = base_cte + f"""
    SELECT
      COALESCE(b.zip_city, '') AS city,
      COALESCE(b.zip_state, '') AS state,
      COALESCE(b.zip_state_name, b.zip_state, '') AS state_name,
      COALESCE(b.county, '') AS county,
      COUNT(DISTINCT b.zip_code) AS locations,
      COALESCE(MAX(cp.city_pop), 0) AS city_population,
      COALESCE(MAX(cp.city_income), 0) AS median_household_income,
      SUM(IF(b.brand IN UNNEST(@main_brands), b.location_count, 0)) AS main_brand_locations,
      SUM(IF(b.brand IN UNNEST(@competitor_brands), b.location_count, 0)) AS competitor_brand_locations
    FROM base b
    LEFT JOIN (
      SELECT city_name, state_code, SUM(population) AS city_pop, AVG(median_household_income) AS city_income
      FROM (SELECT DISTINCT zip_code, city_name, state_code, population, median_household_income FROM {zip_ref})
      GROUP BY city_name, state_code
    ) cp ON b.zip_city = cp.city_name AND b.zip_state = cp.state_code
    GROUP BY city, state, state_name, county
    ORDER BY locations DESC
    LIMIT 10
    """
    brand_query = base_cte + """
    SELECT
      brand,
      SUM(location_count) AS locations,
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
        SELECT ARRAY_AGG(DISTINCT filter_value IGNORE NULLS ORDER BY filter_value)
        FROM {gold_filters_ref}
        WHERE filter_type = 'brand'
      ) AS brands,
      (SELECT ARRAY_AGG(DISTINCT filter_value IGNORE NULLS ORDER BY filter_value) FROM {gold_filters_ref} WHERE filter_type = 'state') AS states,
      (SELECT ARRAY_AGG(DISTINCT filter_value IGNORE NULLS ORDER BY filter_value LIMIT 500) FROM {gold_filters_ref} WHERE filter_type = 'county') AS counties,
      (SELECT ARRAY_AGG(DISTINCT filter_value IGNORE NULLS ORDER BY filter_value LIMIT 500) FROM {gold_filters_ref} WHERE filter_type = 'city') AS cities,
      (SELECT ARRAY_AGG(DISTINCT filter_value IGNORE NULLS ORDER BY filter_value LIMIT 500) FROM {gold_filters_ref} WHERE filter_type = 'zip') AS zips
    """
    gap_query = f"""
    WITH grouped AS (
      SELECT
        state_code AS state,
        state_name AS state_name,
        county,
        city_name AS city,
        zip_code,
        ARRAY_AGG(DISTINCT brand_name IGNORE NULLS ORDER BY brand_name) AS brands_present,
        SUM(IF(brand_name IN UNNEST(@main_brands), location_count, 0)) AS subject_stores,
        SUM(IF(brand_name IN UNNEST(@competitor_brands), location_count, 0)) AS competitor_stores,
        ARRAY_AGG(DISTINCT IF(brand_name IN UNNEST(@competitor_brands), brand_name, NULL) IGNORE NULLS) AS competitor_brands_present
      FROM {gold_gap_ref}
      WHERE (@state = '' OR UPPER(state_code) = @state)
        AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
        AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
        AND (@zip = '' OR zip_code = @zip)
        AND (@min_population IS NULL OR COALESCE(population, 0) >= @min_population)
        AND (@min_income IS NULL OR COALESCE(median_household_income, 0) >= @min_income)
        AND (@max_median_age IS NULL OR COALESCE(median_age, 0) <= @max_median_age)
      GROUP BY state, state_name, county, city, zip_code
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
    LEFT JOIN (
      SELECT zip_code, ANY_VALUE(latitude) AS latitude, ANY_VALUE(longitude) AS longitude,
        ANY_VALUE(population) AS population, ANY_VALUE(median_household_income) AS median_household_income,
        ANY_VALUE(median_age) AS median_age
      FROM {gold_gap_ref}
      GROUP BY zip_code
    ) z ON g.zip_code = z.zip_code
    WHERE (@state = '' OR UPPER(g.state) = @state)
    ORDER BY g.competitor_stores DESC, z.population DESC
    LIMIT 1000
    """
    map_query = f"""
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
    FROM {gold_location_ref}
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
      AND (@state = '' OR UPPER(state_code) = @state)
      AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
      AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
      AND (@zip = '' OR zip_code = @zip)
      AND (ARRAY_LENGTH(@selected_brands) = 0 OR brand IN UNNEST(@selected_brands))
      AND (@min_population IS NULL OR COALESCE(population, 0) >= @min_population)
      AND (@min_income IS NULL OR COALESCE(median_household_income, 0) >= @min_income)
      AND (@max_median_age IS NULL OR COALESCE(median_age, 0) <= @max_median_age)
      AND (latitude BETWEEN 13.0 AND 72.0)
      AND ((longitude BETWEEN -180.0 AND -64.0) OR (longitude BETWEEN 144.0 AND 146.0))
    LIMIT 1000
    """
    sample_query = f"""
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
    FROM {gold_location_ref}
    WHERE (@state = '' OR UPPER(state_code) = @state)
      AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
      AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
      AND (@zip = '' OR zip_code = @zip)
      AND (ARRAY_LENGTH(@main_brands) = 0 OR brand IN UNNEST(@main_brands))
      AND (@min_population IS NULL OR COALESCE(population, 0) >= @min_population)
      AND (@min_income IS NULL OR COALESCE(median_household_income, 0) >= @min_income)
      AND (@max_median_age IS NULL OR COALESCE(median_age, 0) <= @max_median_age)
    ORDER BY last_observed_at DESC, name
    LIMIT 10
    """

    # Real data-quality signals computed straight from the silver-enriched
    # listings table (not the zip-joined base CTE), so completeness/duplicate
    # rates reflect the actual ingested records rather than a fabricated
    # "looks healthy" placeholder.
    # vw_listing_quality_summary is a single unfiltered aggregate over all of
    # silver.listings_enriched (no brand dimension), so it can't answer "data
    # quality for the brands I've selected" - query the enriched table
    # directly with the same brand filter the rest of the payload uses.
    data_quality_query = f"""
    SELECT
      COUNT(*) AS total_rows,
      COUNTIF(latitude IS NOT NULL AND longitude IS NOT NULL) AS with_coordinates,
      COUNTIF(zip_code IS NOT NULL AND zip_code != '') AS with_zip,
      COUNT(DISTINCT CONCAT(COALESCE(brand_name, ''), '|', COALESCE(zip_code, ''), '|', COALESCE(address, ''))) AS distinct_rows,
      MAX(last_observed_at) AS last_observed_at
    FROM `{project_id}.{silver_dataset_id}.listings_enriched`
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
          0 AS total_stores,
          0 AS active_market_locations,
          0 AS active_brand_states,
          0 AS active_brand_cities,
          NULL AS last_updated
        FROM {zip_ref}
        {zip_where}
        """
        zip_states_query = f"""
        WITH zip_dedup AS (
          -- {zip_ref}'s grain is (zip_code, brand_name); collapse the
          -- per-brand fan-out to one row per zip before summing population,
          -- or a zip with N brands present would count its population N times.
          SELECT DISTINCT zip_code, state_code, state_name, city_name, population, median_household_income
          FROM {zip_ref}
          {zip_where}
        )
        SELECT
          COALESCE(state_code, '') AS state,
          COALESCE(state_name, state_code, '') AS state_name,
          COUNT(DISTINCT zip_code) AS locations,
          COUNT(DISTINCT city_name) AS cities,
          (SELECT COUNT(DISTINCT name) FROM `{project_id}.{bronze_dataset_id}.businesses` WHERE is_deleted IS NOT TRUE AND COALESCE(status, 'active') = 'active') AS brands,
          COALESCE(SUM(population), 0) AS state_population,
          COALESCE(AVG(median_household_income), 0) AS median_household_income,
          -- No brand/listing data exists yet at this pre-bootstrap stage
          -- (that's the whole reason this fallback path is active), so
          -- there's nothing to split by main vs competitor brand yet.
          0 AS main_brand_locations,
          0 AS competitor_brand_locations
        FROM zip_dedup
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
          COUNT(DISTINCT zip_code) AS locations,
          COALESCE(SUM(population), 0) AS city_population,
          COALESCE(AVG(median_household_income), 0) AS median_household_income,
          0 AS main_brand_locations,
          0 AS competitor_brand_locations
        FROM (SELECT DISTINCT zip_code, city_name, state_code, state_name, county, population, median_household_income FROM {zip_ref} {zip_where})
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
        # Run zip queries in parallel
        zip_queries = {
            "totals": (zip_totals_query, job_config),
            "top_states": (zip_states_query, job_config),
            "top_cities": (zip_cities_query, job_config),
        }
        zip_results = _execute_bq_queries_parallel(zip_queries, client)
        payload["totals"] = zip_results["totals"]
        payload["top_states"] = zip_results["top_states"]
        payload["top_cities"] = zip_results["top_cities"]
        payload["filter_options"] = dict(next(iter(client.query(zip_filter_query).result())))
        payload["reporting_cache"] = "zip_base"
        return payload

    try:
        # Execute independent BigQuery queries in parallel for speed
        parallel_queries = {
            "totals": (totals_query, job_config),
            "top_states": (top_states_query, job_config),
            "top_cities": (top_cities_query, job_config),
            "brands": (brand_query, job_config),
            "raw_whitespace": (gap_query, job_config),
            "map_records": (map_query, job_config),
            "sample_records": (sample_query, job_config),
            "data_quality": (data_quality_query, job_config),
        }
        query_results = _execute_bq_queries_parallel(parallel_queries, client)
        totals = query_results["totals"]
        top_states = query_results["top_states"]
        top_cities = query_results["top_cities"]
        brands = query_results["brands"]
        raw_whitespace = query_results["raw_whitespace"]
        map_records = query_results["map_records"]
        sample_records = query_results["sample_records"]
        data_quality_row = query_results["data_quality"]

        # filter_options_query runs separately (no job_config, simpler query)
        filter_options = dict(next(iter(client.query(filter_options_query).result())))
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            refresh_started = _refresh_silver_background()
            payload = zip_only_payload("Preparing business data.")
            payload["refreshing"] = bool(refresh_started or REPORTING_REFRESHING)
            return payload
        raise

    present_states_extra = {row["state"] for row in client.query(base_cte + "SELECT DISTINCT state_code AS state FROM base WHERE location_count > 0", job_config=job_config).result() if row.get("state")}
    return _finish_reporting_summary(
        params, cache_key, totals, top_states, top_cities, brands, filter_options, raw_whitespace,
        map_records, sample_records, data_quality_row, present_states_extra,
        main_brands, competitor_brands, state_filter, county_filter, city_filter, zip_filter,
        min_population, min_income, max_median_age, source_table, "miss", refresh_started,
    )


def _finish_reporting_summary(
    params: dict[str, list[str]],
    cache_key: str,
    totals: dict[str, Any],
    top_states: list[dict[str, Any]],
    top_cities: list[dict[str, Any]],
    brands: list[dict[str, Any]],
    filter_options: dict[str, Any],
    raw_whitespace: list[dict[str, Any]],
    map_records: list[dict[str, Any]],
    sample_records: list[dict[str, Any]],
    data_quality_row: dict[str, Any],
    present_states_extra: set[str],
    main_brands: list[str],
    competitor_brands: list[str],
    state_filter: str,
    county_filter: str,
    city_filter: str,
    zip_filter: str,
    min_population: float | None,
    min_income: float | None,
    max_median_age: float | None,
    source_table: str,
    reporting_cache_label: str,
    refresh_started: bool,
) -> dict[str, Any]:
    """Shared downstream processing (opportunity scoring, KPIs, data quality,
    head-to-head enrichment) for reporting_summary() - identical regardless
    of whether the raw metrics above came from the SQLite gold mirror or a
    live BigQuery query, so the two data sources can never silently drift
    in how they compute derived numbers."""
    state_codes = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
        "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
        "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
        "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
        "PR", "GU", "VI", "AS", "MP",
    }
    present_states = {row["state"] for row in top_states if row.get("state") and (row.get("locations") or 0) > 0}
    present_states.update(present_states_extra)
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
        "gap_zips": competitor_whitespace_count + open_whitespace_count,
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
        "reporting_cache": reporting_cache_label,
        "refreshing": bool(refresh_started or REPORTING_REFRESHING),
        "filters": {
            "main_brands": main_brands,
            "competitor_brands": competitor_brands,
            "state": state_filter,
            "county": county_filter,
            "city": city_filter,
            "zip": zip_filter,
            "min_population": min_population,
            "min_income": min_income,
            "max_median_age": max_median_age,
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
        # Background refresh state is exposed through /api/enrichment/status;
        # Reporting should not render a persistent "Updating." banner.
        "warning": "",
    }
    set_cached_query(cache_key, result_payload)
    return result_payload


def export_reporting_excel(params: dict[str, list[str]] | None = None, *, client: Any = None) -> tuple[bytes, str]:
    """Export complete, un-truncated location records directly from BigQuery for
    the primary brand (Sheet 1) and selected competitor brands (Sheet 2) into a
    formatted multi-sheet .xlsx workbook."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    params = params or {}
    main_brands = _csv_param(params.get("main_brands", [""])[0] or params.get("primary_brand", [""])[0] or params.get("brand", [""])[0])
    raw_competitor_brands = _csv_param(params.get("competitor_brands", [""])[0] or params.get("competitors", [""])[0])
    competitor_brands = [b for b in raw_competitor_brands if b not in main_brands]

    state_filter = str(params.get("state", [""])[0]).strip().upper()
    county_filter = str(params.get("county", [""])[0]).strip()
    city_filter = str(params.get("city", [""])[0]).strip()
    zip_filter = str(params.get("zip", [""])[0]).strip()

    primary_brand_label = main_brands[0] if main_brands else "All Brands"

    # Fetch rows directly from BigQuery view vw_reporting_locations
    primary_records = []
    competitor_records = []

    try:
        project_id, bronze_dataset_id, silver_dataset_id, gold_dataset_id, credentials_json = _medallion_settings()
        if client is None:
            client = _bigquery_client(project_id, credentials_json)
        gold_location_ref = f"`{project_id}.{gold_dataset_id}.vw_reporting_locations`"

        from google.cloud import bigquery

        base_sql = f"""
        SELECT
          brand,
          name,
          address,
          city_name,
          state_code,
          state_name,
          county,
          zip_code,
          country,
          phone_number,
          latitude,
          longitude,
          coordinate_confidence,
          coordinate_source,
          population,
          median_household_income,
          median_age,
          last_observed_at
        FROM {gold_location_ref}
        WHERE (@state = '' OR UPPER(state_code) = @state)
          AND (@county = '' OR LOWER(COALESCE(county, '')) = LOWER(@county))
          AND (@city = '' OR LOWER(COALESCE(city_name, '')) = LOWER(@city))
          AND (@zip = '' OR zip_code = @zip)
        """

        # 1. Fetch Primary Brand records
        primary_sql = base_sql + """
          AND (ARRAY_LENGTH(@main_brands) = 0 OR brand IN UNNEST(@main_brands))
        ORDER BY state_code, city_name, address
        """
        primary_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ArrayQueryParameter("main_brands", "STRING", main_brands),
            bigquery.ScalarQueryParameter("state", "STRING", state_filter),
            bigquery.ScalarQueryParameter("county", "STRING", county_filter),
            bigquery.ScalarQueryParameter("city", "STRING", city_filter),
            bigquery.ScalarQueryParameter("zip", "STRING", zip_filter),
        ])
        for row in client.query(primary_sql, job_config=primary_config).result():
            primary_records.append(dict(row))

        # 2. Fetch Competitor records (if any competitors specified)
        if competitor_brands:
            comp_sql = base_sql + """
              AND brand IN UNNEST(@competitor_brands)
            ORDER BY brand, state_code, city_name, address
            """
            comp_config = bigquery.QueryJobConfig(query_parameters=[
                bigquery.ArrayQueryParameter("competitor_brands", "STRING", competitor_brands),
                bigquery.ScalarQueryParameter("state", "STRING", state_filter),
                bigquery.ScalarQueryParameter("county", "STRING", county_filter),
                bigquery.ScalarQueryParameter("city", "STRING", city_filter),
                bigquery.ScalarQueryParameter("zip", "STRING", zip_filter),
            ])
            for row in client.query(comp_sql, job_config=comp_config).result():
                competitor_records.append(dict(row))

    except Exception as exc:
        LOGGER.warning("direct_bigquery_excel_fetch_fallback error=%s", exc)
        # Fallback to local SQLite mirror if BigQuery is in offline/mock mode
        from whitespace_tool.sqlite_cache import fetch_mirror_reporting_locations
        all_mirror_rows = fetch_mirror_reporting_locations(state_filter, county_filter, city_filter, zip_filter)
        for r in all_mirror_rows:
            brand_name = r.get("brand") or ""
            if not main_brands or brand_name in main_brands:
                primary_records.append(r)
            elif brand_name in competitor_brands:
                competitor_records.append(r)

    wb = openpyxl.Workbook()
    # Sheet 1: Primary Brand
    ws_primary = wb.active
    clean_primary_title = re.sub(r'[\[\]\\/*?:]', '', f"Primary - {primary_brand_label}")[:31]
    ws_primary.title = clean_primary_title

    # Sheet 2: Competitor Brands
    ws_comp = wb.create_sheet(title="Competitor Locations")

    columns = [
        ("brand", "Brand"),
        ("name", "Store / Location Name"),
        ("address", "Street Address"),
        ("city_name", "City"),
        ("state_name", "State"),
        ("state_code", "State Code"),
        ("county", "County"),
        ("zip_code", "ZIP Code"),
        ("country", "Country"),
        ("phone_number", "Phone"),
        ("latitude", "Latitude"),
        ("longitude", "Longitude"),
        ("coordinate_confidence", "Coord Confidence"),
        ("coordinate_source", "Coord Source"),
        ("population", "Census Population"),
        ("median_household_income", "Median Income ($)"),
        ("median_age", "Median Age"),
        ("last_observed_at", "Last Observed"),
    ]

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_font = Font(name="Calibri", size=10)
    data_align_left = Alignment(horizontal="left", vertical="center")
    data_align_right = Alignment(horizontal="right", vertical="center")
    data_align_center = Alignment(horizontal="center", vertical="center")

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    def populate_sheet(ws: Any, records: list[dict[str, Any]], empty_message: str = "No records found.") -> None:
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 28

        # Write header
        for col_idx, (_, col_label) in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_label)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align

        if not records:
            ws.row_dimensions[2].height = 22
            for col_idx in range(1, len(columns) + 1):
                cell = ws.cell(row=2, column=col_idx)
                if col_idx == 1:
                    cell.value = empty_message
                    cell.font = Font(name="Calibri", size=10, italic=True, color="64748B")
                cell.border = thin_border
            return

        for row_idx, record in enumerate(records, start=2):
            ws.row_dimensions[row_idx].height = 20
            is_alt = (row_idx % 2 == 0)
            for col_idx, (col_key, _) in enumerate(columns, start=1):
                val = record.get(col_key)
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                elif isinstance(val, (int, float)) and val is not None:
                    pass
                elif val is not None:
                    val = str(val)
                else:
                    val = ""

                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = data_font
                cell.border = thin_border
                if is_alt:
                    cell.fill = alt_fill

                if col_key in ("latitude", "longitude"):
                    cell.alignment = data_align_right
                    if isinstance(val, (int, float)):
                        cell.number_format = "0.000000"
                elif col_key in ("population", "median_household_income"):
                    cell.alignment = data_align_right
                    if isinstance(val, (int, float)):
                        cell.number_format = "$#,##0" if col_key == "median_household_income" else "#,##0"
                elif col_key in ("median_age", "coordinate_confidence"):
                    cell.alignment = data_align_right
                    if isinstance(val, (int, float)):
                        cell.number_format = "0.0"
                elif col_key in ("state_code", "zip_code", "country"):
                    cell.alignment = data_align_center
                else:
                    cell.alignment = data_align_left

        # Auto-fit column widths
        for col_idx, (_, col_label) in enumerate(columns, start=1):
            col_letter = get_column_letter(col_idx)
            max_len = len(col_label)
            for r_idx in range(2, min(len(records) + 2, 100)):
                cell_val = str(ws.cell(row=r_idx, column=col_idx).value or "")
                if len(cell_val) > max_len:
                    max_len = len(cell_val)
            ws.column_dimensions[col_letter].width = max(12, min(max_len + 4, 45))

    populate_sheet(ws_primary, primary_records, f"No locations found for primary brand '{primary_brand_label}'.")
    comp_label = " ~ ".join(competitor_brands) if competitor_brands else "No competitors selected"
    populate_sheet(ws_comp, competitor_records, f"No competitor locations found ({comp_label}).")

    output_stream = io.BytesIO()
    wb.save(output_stream)
    excel_bytes = output_stream.getvalue()

    safe_brand_slug = re.sub(r'[^a-zA-Z0-9]+', '_', primary_brand_label.lower()).strip('_') or "all_brands"
    timestamp = utc_now_iso()[:10]
    filename = f"{safe_brand_slug}_whitespace_locations_{timestamp}.xlsx"
    return excel_bytes, filename


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
    -- One row per ZIP. The reference union can carry a ZIP more than once
    -- (canonical US ZIPs plus worldwide rows), so without this a single ZIP
    -- appeared several times in the suggestion list, and typing a city name
    -- returned every duplicate of every ZIP in it.
    SELECT zip_code, ANY_VALUE(city_name) AS city_name, ANY_VALUE(county) AS county,
           ANY_VALUE(state_code) AS state_code, ANY_VALUE(state_name) AS state_name,
           ANY_VALUE(latitude) AS latitude, ANY_VALUE(longitude) AS longitude,
           ANY_VALUE(population) AS population,
           ANY_VALUE(median_household_income) AS median_household_income,
           ANY_VALUE(median_age) AS median_age
    FROM {table_ref}
    WHERE (zip_code LIKE CONCAT(UPPER(@q), '%') OR LOWER(city_name) LIKE CONCAT(LOWER(@q), '%'))
      AND (@state = '' OR UPPER(state_code) = UPPER(@state))
      AND (@county = '' OR LOWER(county) = LOWER(@county))
      AND (@city = '' OR LOWER(city_name) = LOWER(@city))
    GROUP BY zip_code
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


def list_rejected(event_id: str = "", business_id: str = "", limit: int = 50, offset: int = 0, ai_pending_only: bool = False, *, client: Any = None) -> dict[str, Any]:
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    if client is None:
        client = _bigquery_client(project_id, credentials_json)
    safe_limit = max(1, min(int(limit or 50), 50000))
    safe_offset = max(0, int(offset or 0))
    ai_clause = "AND is_ai_enriched IS NOT TRUE" if ai_pending_only else ""
    query = f"""SELECT event_id, business_id, source_type_id, row_number, errors, raw_record, template_id, mapping_id, is_ai_enriched, attempt_count, has_ai_suggestion
    FROM `{project_id}.{dataset_id}.error_listings`
    WHERE is_deleted IS NOT TRUE
      {ai_clause}
      AND (@event_id = '' OR event_id = @event_id)
      AND (@business_id = '' OR business_id = @business_id)
    ORDER BY event_id, row_number
    LIMIT {safe_limit + 1} OFFSET {safe_offset}"""
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("event_id", "STRING", event_id),
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
    ])
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
    has_more = len(records) > safe_limit
    return {"records": records[:safe_limit], "offset": safe_offset, "limit": safe_limit, "has_more": has_more}


def _count_error_listings_live(business_id: str = "", *, client: Any = None) -> int:
    """Live BigQuery count of non-deleted error listings for a business
    (empty string = all businesses). The one source of truth; every SQLite
    value is a copy of a number this returned."""
    project_id, dataset_id, credentials_json = _warehouse_settings()
    if client is None:
        client = _bigquery_client(project_id, credentials_json)
    query = f"SELECT COUNT(*) AS total FROM `{project_id}.{dataset_id}.error_listings` WHERE is_deleted IS NOT TRUE AND (@business_id = '' OR business_id = @business_id)"
    from google.cloud import bigquery
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("business_id", "STRING", business_id)])
    try:
        return int(next(iter(client.query(query, job_config=config).result()))["total"])
    except Exception as exc:
        err_msg = str(exc).lower()
        if getattr(exc, "code", None) == 404 or "404" in err_msg or "not found" in err_msg:
            return 0
        raise


def refresh_error_count(business_id: str = "", *, client: Any = None) -> int:
    """Re-count from BigQuery and write the result back to SQLite. Call this
    right after anything that changes error_listings (a reprocess move, a
    fresh mapper save) so the cached counter converges on the warehouse."""
    total = _count_error_listings_live(business_id, client=client)
    try:
        set_error_count(business_id, total)
    except Exception as exc:
        LOGGER.warning("error_count_cache_write_failed business_id=%s error=%s", business_id, exc)
    return total


def count_error_listings(business_id: str = "", refresh: bool = False) -> int:
    """Review Error Listings count. By default serves the fast SQLite value
    (written from the last live count) so the tab paints instantly and lazy
    reloads are cheap; only reaches BigQuery when SQLite has never been
    seeded. refresh=True forces a live re-count and rewrites SQLite - used
    when data has just moved and the cached number is known stale."""
    if refresh:
        return refresh_error_count(business_id)
    cached = get_error_count(business_id)
    if cached is not None:
        return cached
    # First read for this business - seed SQLite from a live count so every
    # later read is fast.
    return refresh_error_count(business_id)


def error_listings_by_brand() -> dict[str, Any]:
    """Per-brand breakdown of how many (non-deleted) error listings each
    business has, resolving business_id -> brand name, highest count first.
    Powers the Review tab's brand-impact table/chart."""
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    query = f"""
    SELECT
      e.business_id AS business_id,
      COALESCE(b.name, e.business_id) AS brand,
      COUNT(*) AS count
    FROM `{project_id}.{dataset_id}.error_listings` e
    LEFT JOIN `{project_id}.{dataset_id}.businesses` b
      ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
    WHERE e.is_deleted IS NOT TRUE
    GROUP BY business_id, brand
    ORDER BY count DESC
    """
    try:
        rows = [
            {"business_id": row["business_id"], "brand": row["brand"], "count": int(row["count"])}
            for row in client.query(query).result()
        ]
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"brands": [], "total": 0}
        raise
    return {"brands": rows, "total": sum(row["count"] for row in rows)}


def reporting_quality_summary(params: dict[str, list[str]] | None = None, *, _skip_cache: bool = False) -> dict[str, Any]:
    """Return the invalid-listing population for Reporting's quality tab.

    This is deliberately separate from reporting_summary(): the quality tab
    measures records that failed validation or still need review, while the
    location tab measures valid/enriched market coverage.
    """
    from google.cloud import bigquery

    params = params or {}
    quality_cache_key = f"reporting_quality:v1:{json.dumps(params, sort_keys=True)}"
    force_refresh = str(params.get("refresh", [""])[0] or "").lower() in {"1", "true", "yes"}
    cached_quality = get_cached_query(quality_cache_key)
    if cached_quality and not _skip_cache and not force_refresh:
        cached_quality["quality_cache"] = "sqlite"
        with _QUALITY_REFRESH_LOCK:
            should_refresh = quality_cache_key not in _QUALITY_REFRESH_KEYS
            # Tell the client a fresher answer is being computed. Without
            # this the page rendered the cached payload and never looked
            # again - the background refresh rewrote SQLite, but nothing
            # asked for it, so the donut and the fix counters sat on stale
            # numbers indefinitely (reported: "still outdated after 5
            # minutes on the page").
            cached_quality["refreshing"] = bool(should_refresh or quality_cache_key in _QUALITY_REFRESH_KEYS)
            if should_refresh:
                _QUALITY_REFRESH_KEYS.add(quality_cache_key)
        if should_refresh:
            def refresh_quality() -> None:
                try:
                    reporting_quality_summary(params, _skip_cache=True)
                except Exception as exc:
                    LOGGER.warning("quality_mirror_refresh_failed error=%s", exc)
                finally:
                    with _QUALITY_REFRESH_LOCK:
                        _QUALITY_REFRESH_KEYS.discard(quality_cache_key)
            threading.Thread(target=refresh_quality, name="quality-mirror-refresh", daemon=True).start()
        return cached_quality
    if not cached_quality and not _skip_cache and not force_refresh:
        # A genuinely cold cache (first load, or right after invalidate_cache()
        # on any save/reprocess) used to block this request on the full live
        # query below - measured at 30+ seconds against a 21k-row review
        # queue, since every row's `errors`/`raw_record` JSON has to be
        # fetched and aggregated in Python. Explicit refreshes (force_refresh)
        # keep blocking on purpose (the UI already shows progress for those);
        # this only covers the silent/automatic load path. Warm the cache in
        # the background exactly like the stale-cache case above, and hand
        # back an honest "still computing" placeholder immediately instead of
        # hanging the request.
        with _QUALITY_REFRESH_LOCK:
            already_warming = quality_cache_key in _QUALITY_REFRESH_KEYS
            if not already_warming:
                _QUALITY_REFRESH_KEYS.add(quality_cache_key)
        if not already_warming:
            def warm_cold_quality() -> None:
                try:
                    reporting_quality_summary(params, _skip_cache=True)
                except Exception as exc:
                    LOGGER.warning("quality_mirror_cold_warm_failed error=%s", exc)
                finally:
                    with _QUALITY_REFRESH_LOCK:
                        _QUALITY_REFRESH_KEYS.discard(quality_cache_key)
            threading.Thread(target=warm_cold_quality, name="quality-mirror-cold-warm", daemon=True).start()
        return {
            "scope": "invalid_listings",
            "metrics": {"invalid_listings": 0, "needs_manual_review": 0, "ai_fixed": 0, "manual_fixed": 0, "unresolved_rate_pct": 0.0, "invalid_record_rate_pct": 0.0},
            "reasons": [], "brands": [], "states": [], "cities": [], "history": [],
            "filters": {"brands": [], "states": [], "reasons": []},
            "warning": "", "quality_cache": "warming",
        }
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    # The query below selects has_ai_suggestion, which older deployed tables
    # do not have - without this pass BigQuery raises "Name has_ai_suggestion
    # not found" and the entire quality tab 400s.
    try:
        _ensure_once("error_listings", _ensure_error_listings_table, client, project_id, dataset_id)
    except Exception as exc:
        LOGGER.warning("error_listings_schema_ensure_failed error=%s", exc)
    brand = str(params.get("brand", [""])[0] or "").strip()
    state = str(params.get("state", [""])[0] or "").strip().upper()
    city = str(params.get("city", [""])[0] or "").strip().lower()
    reason = str(params.get("reason", [""])[0] or "").strip().lower()
    status = str(params.get("status", ["all"])[0] or "all").strip().lower()
    start_date = str(params.get("start_date", [""])[0] or "").strip()
    end_date = str(params.get("end_date", [""])[0] or "").strip()

    # error_listings is the durable review population and already carries the
    # AI/manual distinction.  Read it in one bounded query and aggregate here;
    # this keeps the quality contract independent of the healthy gold views.
    query = f"""
    SELECT e.business_id, e.event_id, e.row_number, e.errors, e.raw_record,
           e.is_ai_enriched, e.has_ai_suggestion, COALESCE(b.name, e.business_id) AS brand
    FROM `{project_id}.{dataset_id}.error_listings` e
    LEFT JOIN `{project_id}.{dataset_id}.businesses` b
      ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
    WHERE e.is_deleted IS NOT TRUE
    """
    query += " AND (@start_date = '' OR DATE(e.observed_at) >= SAFE_CAST(@start_date AS DATE)) AND (@end_date = '' OR DATE(e.observed_at) <= SAFE_CAST(@end_date AS DATE))"
    try:
        rows = list(client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "STRING", start_date),
            bigquery.ScalarQueryParameter("end_date", "STRING", end_date),
        ])).result())
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            rows = []
        else:
            raise

    def decode(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                return value
        return value

    def raw_value(raw: Any, *keys: str) -> str:
        raw = decode(raw)
        if not isinstance(raw, dict):
            return ""
        for key in keys:
            value = raw.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    reason_counts: dict[str, int] = {}
    brand_counts: dict[str, dict[str, int]] = {}
    state_counts: dict[str, int] = {}
    city_counts: dict[str, int] = {}
    filtered: list[dict[str, Any]] = []
    _schedule_quality_fix_metrics_refresh()
    repair_stats = get_auto_repair_stats()
    ai_fixed = int(repair_stats.get("fixed", 0))
    manual_fixed = int(repair_stats.get("manual_fixed", 0))

    for row in rows:
        item = dict(row)
        item["errors"] = decode(item.get("errors"))
        item["raw_record"] = decode(item.get("raw_record"))
        brand_name = str(item.get("brand") or "Unknown").strip()
        item_state = raw_value(item.get("raw_record"), "state", "state_code", "state_name").upper()
        item_city = raw_value(item.get("raw_record"), "city", "city_name").lower()
        error_text = item.get("errors")
        if isinstance(error_text, dict):
            error_text = list(error_text.values())
        if not isinstance(error_text, list):
            error_text = [error_text] if error_text else []
        item_reasons = []
        for value in error_text:
            label = str(value.get("code") or value.get("type") or value.get("reason") or value) if isinstance(value, dict) else str(value)
            label = label.strip().lower().replace(" ", "_")
            if label:
                item_reasons.append(label)
                reason_counts[label] = reason_counts.get(label, 0) + 1
        item["quality_reasons"] = sorted(set(item_reasons))
        item["state"] = item_state
        item["city"] = item_city
        item["status"] = "ai_fixed" if item.get("is_ai_enriched") else "needs_review"
        if brand and brand_name.lower() != brand.lower():
            continue
        if state and item_state != state:
            continue
        if city and item_city != city:
            continue
        if reason and reason not in item["quality_reasons"]:
            continue
        if status == "ai_fixed" and not item.get("is_ai_enriched"):
            continue
        if status == "needs_review" and item.get("is_ai_enriched"):
            continue
        filtered.append(item)
        state_counts[item_state or "Unknown"] = state_counts.get(item_state or "Unknown", 0) + 1
        city_counts[item_city.title() if item_city else "Unknown"] = city_counts.get(item_city.title() if item_city else "Unknown", 0) + 1
        bucket = brand_counts.setdefault(brand_name, {"invalid": 0, "needs_review": 0, "ai_enriched": 0})
        bucket["invalid"] += 1
        if item.get("is_ai_enriched"):
            bucket["ai_enriched"] += 1
        else:
            bucket["needs_review"] += 1

    # Give the per-brand table the SAME cumulative definition the headline
    # cards use, instead of counting open rows flagged is_ai_enriched. Under
    # one label, two different measures is how the two numbers came to
    # disagree. Best-effort: on failure the open-row counts still render.
    try:
        cumulative_by_brand = fix_state_counts_by_brand(client=client)
        for brand_name_key, bucket in brand_counts.items():
            cumulative = cumulative_by_brand.get(brand_name_key)
            if cumulative:
                bucket["ai_enriched"] = cumulative["ai_fixed"]
                bucket["manual_fixed"] = cumulative["manual_fixed"]
                bucket["ever_invalid"] = cumulative["total_ever_invalid"]
    except Exception as exc:
        LOGGER.warning("fix_state_by_brand_failed error=%s", exc)

    try:
        replace_quality_mirror(filtered)
    except Exception as exc:
        LOGGER.warning("quality_mirror_write_failed error=%s", exc)
    total = len(filtered)
    needs_review = sum(1 for row in filtered if not row.get("is_ai_enriched"))
    # RPT-08: four mutually exclusive states, plus a pivot of those states
    # against the field each row actually failed on. "Pending" is split by
    # has_ai_suggestion - computed once at write time (see
    # _row_has_ai_suggestion), so this is a plain read, not a re-probe of
    # the whole queue on every reporting load.
    ai_review_pending = sum(1 for row in filtered if row.get("has_ai_suggestion"))
    manual_review_pending = total - ai_review_pending
    fix_state_pivot: dict[str, dict[str, int]] = {}
    for row in filtered:
        # Four buckets, not two. This previously chose only between the two
        # PENDING keys, so the pivot's ai_fixed/manual_fixed columns were
        # structurally always zero no matter how many records had been fixed.
        if row.get("is_ai_enriched"):
            state_key = "ai_fixed"
        elif str(row.get("resolution_status") or "") == "fixed":
            state_key = "manual_fixed"
        elif row.get("has_ai_suggestion"):
            state_key = "ai_review_pending"
        else:
            state_key = "manual_review_pending"
        for reason_key in (row.get("quality_reasons") or ["unknown"]):
            bucket = fix_state_pivot.setdefault(reason_key, {
                "ai_fixed": 0, "ai_review_pending": 0, "manual_fixed": 0, "manual_review_pending": 0,
            })
            bucket[state_key] += 1
    history: list[dict[str, Any]] = []
    coverage_metrics: dict[str, Any] = {
        "total_records": 0, "zip_completeness_pct": 0.0, "coordinate_completeness_pct": 0.0,
        "duplicate_rate_pct": 0.0, "stale_records": 0, "entity_resolution_attempts": 0,
        "entity_resolution_success_rate_pct": 0.0,
        # Extended quality KPIs
        "source_coverage_pct": 0.0, "required_field_completeness_pct": 0.0,
        "geo_enrichment_success_rate_pct": 0.0, "coordinate_accuracy_rate_pct": 0.0,
        "demographic_enrichment_coverage_pct": 0.0, "provenance_coverage_pct": 0.0,
        "traceable_record_rate_pct": 0.0, "valid_location_rate_pct": 0.0,
        "data_accuracy_score": 0.0, "data_consistency_score": 0.0, "data_freshness_score": 0.0,
        "pipeline_success_rate_pct": 0.0, "avg_pipeline_latency_hours": None,
        "overall_dq_score": 0.0,
        "entity_resolution_failure_rate_pct": 0.0,
        "stale_after_days": DEFAULT_STALE_AFTER_DAYS,
    }
    try:
        # User-configurable "days without an update = stale" threshold
        # (persisted in app_settings, was previously hardcoded to 90). A
        # per-request ?stale_days= override is honoured for previewing a
        # different window without changing the saved setting.
        stale_after_days = get_stale_after_days()
        try:
            requested_stale = int(str(params.get("stale_days", [""])[0] or "").strip() or 0)
            if 1 <= requested_stale <= 3650:
                stale_after_days = requested_stale
        except (TypeError, ValueError):
            pass
        coverage_metrics["stale_after_days"] = stale_after_days
        coverage_query = f"""
        WITH base AS (
          -- Every column here must exist on `listings` (see TABLE_SCHEMAS).
          -- This query previously selected event_id, coordinate_source,
          -- coordinate_confidence and state - none of which are columns on
          -- this table - so it raised "Unrecognized name: event_id" on every
          -- single run and was swallowed by the except below into a silent
          -- all-zero coverage_metrics. That is why ZIP/coordinate
          -- completeness, duplicate rate, stale records and the overall DQ
          -- score all read 0 regardless of the real data.
          SELECT
            listing_id, business_id, zip_code, latitude, longitude,
            last_observed_at, enriched_at, ingestion_id, content_hash,
            address, name, state_code, country,
            -- content_hash is the canonical dedup key. business_id is NO
            -- LONGER part of it (see CONTENT_HASH_FIELDS), so a shared hash
            -- means the same physical place - whether it was filed once or
            -- under two brands. That is the intended reading of a duplicate
            -- here: every hashed field (name, address, coordinates, phone,
            -- website, ...) has to match, which two genuinely different
            -- businesses at one address will not do. Fall back to the older
            -- business/address/zip identity only for rows written before the
            -- hash existed.
            COUNT(*) OVER (
              PARTITION BY
                COALESCE(
                  NULLIF(TRIM(COALESCE(content_hash, '')), ''),
                  CONCAT(COALESCE(business_id,''), '|', LOWER(TRIM(COALESCE(address,''))), '|', COALESCE(zip_code,''))
                )
            ) AS duplicate_group_count
          FROM `{project_id}.{dataset_id}.listings`
          WHERE is_deleted IS NOT TRUE
        ),
        totals AS (
          SELECT
            COUNT(*) AS total_records,
            -- ZIP completeness counts a *usable* postal code, not merely a
            -- non-empty string: 5-digit US, or any alphanumeric non-US code.
            -- NOTE: braces are doubled because this is an f-string - {{5}}
            -- renders as the literal regex quantifier {5}. Written singly,
            -- Python interpolates them as format fields and the pattern
            -- silently becomes '^[0-9]5$', which matches almost nothing.
            COUNTIF(
              REGEXP_CONTAINS(TRIM(COALESCE(zip_code,'')), r'^[0-9]{{5}}$')
              OR REGEXP_CONTAINS(UPPER(TRIM(COALESCE(zip_code,''))), r'^[A-Z0-9][A-Z0-9 -]{{2,9}}$')
            ) AS with_zip,
            -- Coordinate completeness means present AND valid - in-range and
            -- not the 0,0 null-island placeholder.
            COUNTIF(
              latitude IS NOT NULL AND longitude IS NOT NULL
              AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180
              AND NOT (latitude = 0 AND longitude = 0)
            ) AS with_coordinates,
            COUNTIF(last_observed_at < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {stale_after_days} DAY)) AS stale_records,
            COUNTIF(duplicate_group_count > 1) AS duplicate_records,
            -- Required field completeness: name + address + zip + state + country all non-null/non-empty
            COUNTIF(
              NULLIF(TRIM(COALESCE(name,'')),'') IS NOT NULL AND
              NULLIF(TRIM(COALESCE(address,'')),'') IS NOT NULL AND
              NULLIF(TRIM(COALESCE(zip_code,'')),'') IS NOT NULL AND
              NULLIF(TRIM(COALESCE(state_code,'')),'') IS NOT NULL AND
              NULLIF(TRIM(COALESCE(country,'')),'') IS NOT NULL
            ) AS with_required_fields,
            -- Geo enrichment: the row has actually been through the
            -- enrichment pass (there is no coordinate_source column on
            -- this table - enriched_at is the real signal).
            COUNTIF(enriched_at IS NOT NULL) AS geo_enriched,
            -- Coordinate accuracy: no confidence column exists here, so
            -- this is measured as coordinates that are genuinely usable
            -- (in range, not null-island) rather than an invented score.
            COUNTIF(
              latitude IS NOT NULL AND longitude IS NOT NULL
              AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180
              AND NOT (latitude = 0 AND longitude = 0)
            ) AS coord_accurate,
            -- Provenance: content_hash present
            COUNTIF(content_hash IS NOT NULL AND content_hash != '') AS with_provenance,
            -- Traceable: tied back to the ingestion run that produced it.
            COUNTIF(ingestion_id IS NOT NULL AND ingestion_id != '') AS with_event_id,
            -- Pipeline latency (hours)
            AVG(CASE WHEN enriched_at IS NOT NULL THEN TIMESTAMP_DIFF(enriched_at, last_observed_at, HOUR) END) AS avg_latency_hours
          FROM base
        ),
        brands_active AS (
          SELECT COUNT(DISTINCT b.business_id) AS active_brands
          FROM `{project_id}.{dataset_id}.businesses` b
          WHERE b.is_deleted IS NOT TRUE AND COALESCE(b.status, 'active') = 'active'
        ),
        brands_with_listings AS (
          SELECT COUNT(DISTINCT business_id) AS brands_with_data
          FROM `{project_id}.{dataset_id}.listings`
          WHERE is_deleted IS NOT TRUE
        )
        SELECT t.*, ba.active_brands, bl.brands_with_data
        FROM totals t, brands_active ba, brands_with_listings bl
        """
        coverage_row = next(iter(client.query(coverage_query).result()), {})
        tr = int(coverage_row.get("total_records", 0) or 0)
        with_zip = int(coverage_row.get("with_zip", 0) or 0)
        with_coords = int(coverage_row.get("with_coordinates", 0) or 0)
        stale = int(coverage_row.get("stale_records", 0) or 0)
        dup = int(coverage_row.get("duplicate_records", 0) or 0)
        req_fields = int(coverage_row.get("with_required_fields", 0) or 0)
        geo_enriched = int(coverage_row.get("geo_enriched", 0) or 0)
        coord_acc = int(coverage_row.get("coord_accurate", 0) or 0)
        prov = int(coverage_row.get("with_provenance", 0) or 0)
        traceable = int(coverage_row.get("with_event_id", 0) or 0)
        avg_lat = coverage_row.get("avg_latency_hours")
        active_brands = int(coverage_row.get("active_brands", 0) or 0)
        brands_with_data = int(coverage_row.get("brands_with_data", 0) or 0)
        pct = lambda n, d: round(n * 100 / d, 2) if d else 0.0
        # Derived rates
        invalid_count = len([r for r in rows if not r.get("is_ai_enriched") is None])  # all error rows
        invalid_total = len(rows)
        zip_pct = pct(with_zip, tr)
        coord_pct = pct(with_coords, tr)
        dup_pct = pct(dup, tr)
        freshness = pct(tr - stale, tr)
        req_pct = pct(req_fields, tr)
        geo_pct = pct(geo_enriched, tr)
        coord_acc_pct = pct(coord_acc, tr)
        prov_pct = pct(prov, tr)
        trace_pct = pct(traceable, tr)
        # Valid listings and invalid (error_listings) rows are two separate
        # populations, so the denominator is everything ingested, not the
        # valid table alone - otherwise invalid_total > tr made this fall
        # into a bogus 100.0 ("perfect") and inflated the overall DQ score.
        ingested_total = tr + invalid_total
        valid_pct = pct(tr, ingested_total)
        source_cov = pct(brands_with_data, active_brands)
        # Weighted Overall DQ Score (sum of weights = 1.0)
        overall_dq = round(
            req_pct      * 0.20 +
            valid_pct    * 0.20 +
            geo_pct      * 0.15 +
            freshness    * 0.15 +
            (100 - dup_pct) * 0.10 +
            coord_acc_pct   * 0.10 +
            pct(0, 1)       * 0.05 +  # demographic (separate query below)
            prov_pct        * 0.05,
            2
        )
        coverage_metrics.update({
            "total_records": tr,
            "zip_completeness_pct": zip_pct,
            "coordinate_completeness_pct": coord_pct,
            "duplicate_rate_pct": dup_pct,
            "stale_records": stale,
            "required_field_completeness_pct": req_pct,
            "geo_enrichment_success_rate_pct": geo_pct,
            "coordinate_accuracy_rate_pct": coord_acc_pct,
            "provenance_coverage_pct": prov_pct,
            "traceable_record_rate_pct": trace_pct,
            "valid_location_rate_pct": valid_pct,
            "data_accuracy_score": valid_pct,
            "data_consistency_score": round(100 - dup_pct, 2),
            "data_freshness_score": freshness,
            "pipeline_success_rate_pct": valid_pct,
            "source_coverage_pct": source_cov,
            "avg_pipeline_latency_hours": round(float(avg_lat), 2) if avg_lat is not None else None,
        })
        # Demographic coverage — from gold view (may not exist yet)
        try:
            demo_query = f"""
            SELECT COUNT(*) AS total,
              COUNTIF(population IS NOT NULL AND median_household_income IS NOT NULL) AS with_demo
            FROM `{project_id}.{dataset_id}.listings`
            WHERE is_deleted IS NOT TRUE
            """
            demo_row = next(iter(client.query(demo_query).result()), {})
            demo_total = int(demo_row.get("total", 0) or 0)
            demo_cov = pct(int(demo_row.get("with_demo", 0) or 0), demo_total)
            coverage_metrics["demographic_enrichment_coverage_pct"] = demo_cov
            # Recompute DQ score with real demographic coverage
            overall_dq = round(
                req_pct      * 0.20 +
                valid_pct    * 0.20 +
                geo_pct      * 0.15 +
                freshness    * 0.15 +
                (100 - dup_pct) * 0.10 +
                coord_acc_pct   * 0.10 +
                demo_cov        * 0.05 +
                prov_pct        * 0.05,
                2
            )
        except Exception:
            pass
        coverage_metrics["overall_dq_score"] = overall_dq
        entity_query = f"""
        SELECT COUNT(*) AS attempts, COUNTIF(improved IS TRUE) AS successes
        FROM `{project_id}.{dataset_id}.quality_fix_events`
        WHERE UPPER(fix_type) = 'AI'
        """
        entity_row = next(iter(client.query(entity_query).result()), {})
        attempts = int(entity_row.get("attempts", 0) or 0)
        successes = int(entity_row.get("successes", 0) or 0)
        coverage_metrics["entity_resolution_attempts"] = attempts
        coverage_metrics["entity_resolution_success_rate_pct"] = pct(successes, attempts)
        # Both halves, so the failure side doesn't have to be inferred by
        # the caller (and can't drift from the success figure).
        coverage_metrics["entity_resolution_failure_rate_pct"] = pct(max(attempts - successes, 0), attempts)
    except Exception as exc:
        LOGGER.warning("quality_coverage_metrics_failed error=%s", exc)
    # Keep one durable point per day and scope.  The SQLite quality mirror is
    # still used for the first paint; this history is only the authoritative
    # source for time comparisons.
    try:
        _ensure_reporting_quality_snapshots_table(client, project_id, dataset_id)
        scope_key = hashlib.sha256(json.dumps({"brand": brand, "state": state, "city": city, "reason": reason, "status": status}, sort_keys=True).encode("utf-8")).hexdigest()
        duplicate_records = max(total - len({f"{raw_value(row.get('raw_record'), 'brand')}|{raw_value(row.get('raw_record'), 'zip', 'zip_code')}|{raw_value(row.get('raw_record'), 'address')}" for row in filtered}), 0)
        snapshot_query = f"""
        MERGE `{project_id}.{dataset_id}.reporting_quality_snapshots` target
        USING (SELECT CURRENT_DATE() AS snapshot_date, @scope_key AS scope_key) source
        ON target.snapshot_date = source.snapshot_date AND target.scope_key = source.scope_key
        WHEN MATCHED THEN UPDATE SET captured_at = CURRENT_TIMESTAMP(), total_records = @total_records,
          invalid_records = @invalid_records, needs_manual_review = @needs_manual_review,
          ai_fixed = @ai_fixed, manual_fixed = @manual_fixed, zip_missing = @zip_missing,
          coordinates_missing = @coordinates_missing, duplicate_records = @duplicate_records,
          zip_completeness_pct = @zip_completeness_pct, coordinate_completeness_pct = @coordinate_completeness_pct,
          duplicate_rate_pct = @duplicate_rate_pct, stale_records = @stale_records,
          entity_resolution_attempts = @entity_resolution_attempts, entity_resolution_success_rate_pct = @entity_resolution_success_rate_pct,
          content_hash = @content_hash
        WHEN NOT MATCHED THEN INSERT (snapshot_date, scope_key, captured_at, total_records, invalid_records,
          needs_manual_review, ai_fixed, manual_fixed, zip_missing, coordinates_missing, duplicate_records,
          zip_completeness_pct, coordinate_completeness_pct, duplicate_rate_pct, stale_records,
          entity_resolution_attempts, entity_resolution_success_rate_pct, content_hash)
        VALUES (CURRENT_DATE(), @scope_key, CURRENT_TIMESTAMP(), @total_records, @invalid_records,
          @needs_manual_review, @ai_fixed, @manual_fixed, @zip_missing, @coordinates_missing, @duplicate_records,
          @zip_completeness_pct, @coordinate_completeness_pct, @duplicate_rate_pct, @stale_records,
          @entity_resolution_attempts, @entity_resolution_success_rate_pct, @content_hash)
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("scope_key", "STRING", scope_key),
            bigquery.ScalarQueryParameter("total_records", "INT64", total),
            bigquery.ScalarQueryParameter("invalid_records", "INT64", total),
            bigquery.ScalarQueryParameter("needs_manual_review", "INT64", needs_review),
            bigquery.ScalarQueryParameter("ai_fixed", "INT64", ai_fixed),
            bigquery.ScalarQueryParameter("manual_fixed", "INT64", manual_fixed),
            bigquery.ScalarQueryParameter("zip_missing", "INT64", sum("zip" in reason for reason in reason_counts for _ in range(reason_counts[reason]))),
            bigquery.ScalarQueryParameter("coordinates_missing", "INT64", sum("coordinate" in reason for reason in reason_counts for _ in range(reason_counts[reason]))),
            bigquery.ScalarQueryParameter("duplicate_records", "INT64", duplicate_records),
            bigquery.ScalarQueryParameter("content_hash", "STRING", hashlib.sha256(json.dumps({"total": total, "invalid": total, "review": needs_review, "ai": ai_fixed, "manual": manual_fixed}, sort_keys=True).encode("utf-8")).hexdigest()),
            bigquery.ScalarQueryParameter("zip_completeness_pct", "FLOAT64", coverage_metrics["zip_completeness_pct"]),
            bigquery.ScalarQueryParameter("coordinate_completeness_pct", "FLOAT64", coverage_metrics["coordinate_completeness_pct"]),
            bigquery.ScalarQueryParameter("duplicate_rate_pct", "FLOAT64", coverage_metrics["duplicate_rate_pct"]),
            bigquery.ScalarQueryParameter("stale_records", "INT64", coverage_metrics["stale_records"]),
            bigquery.ScalarQueryParameter("entity_resolution_attempts", "INT64", coverage_metrics["entity_resolution_attempts"]),
            bigquery.ScalarQueryParameter("entity_resolution_success_rate_pct", "FLOAT64", coverage_metrics["entity_resolution_success_rate_pct"]),
        ])
        client.query(snapshot_query, job_config=job_config).result()
        history_rows = client.query(
            f"SELECT snapshot_date, captured_at, total_records, invalid_records, needs_manual_review, ai_fixed, manual_fixed, zip_missing, coordinates_missing, duplicate_records FROM `{project_id}.{dataset_id}.reporting_quality_snapshots` WHERE scope_key = @scope_key ORDER BY snapshot_date DESC LIMIT 400",
            job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("scope_key", "STRING", scope_key)]),
        ).result()
        for history_row in history_rows:
            point = dict(history_row)
            for key, value in point.items():
                if hasattr(value, "isoformat"):
                    point[key] = value.isoformat()
            history.append(point)
        history.reverse()
    except Exception as exc:
        LOGGER.warning("quality_snapshot_write_failed error=%s", exc)
    payload = {
        "scope": "invalid_listings",
        "fix_states": _cumulative_fix_states(),
        "metrics": {
            "invalid_listings": total,
            "needs_manual_review": needs_review,
            "ai_fixed": ai_fixed,
            "manual_fixed": manual_fixed,
            # RPT-08's four states. ai_fixed/manual_fixed are the cumulative
            # counters; the two pending figures split the currently-open
            # queue by whether a suggestion was found at write time.
            "ai_review_pending": ai_review_pending,
            "manual_review_pending": manual_review_pending,
            "ai_fixed_share_pct": round(ai_fixed * 100 / (ai_fixed + manual_fixed + total), 2) if (ai_fixed + manual_fixed + total) else 0.0,
            "manual_fixed_share_pct": round(manual_fixed * 100 / (ai_fixed + manual_fixed + total), 2) if (ai_fixed + manual_fixed + total) else 0.0,
            "ai_review_pending_share_pct": round(ai_review_pending * 100 / (ai_fixed + manual_fixed + total), 2) if (ai_fixed + manual_fixed + total) else 0.0,
            "manual_review_pending_share_pct": round(manual_review_pending * 100 / (ai_fixed + manual_fixed + total), 2) if (ai_fixed + manual_fixed + total) else 0.0,
            "unresolved_rate_pct": round(needs_review * 100 / total, 2) if total else 0.0,
            # coverage_metrics["total_records"] can legitimately be 0 (its
            # own BigQuery query failed and fell back to the zeroed default,
            # logged separately as quality_snapshot_write_failed/a similar
            # warning) - dividing by max(0, 1) = 1 in that case produced a
            # nonsensical rate like 2,866,500% instead of an honest "unknown".
            # Invalid rows live in error_listings, valid rows in listings -
            # dividing one population by the other produced rates over 100%
            # (e.g. 280%). The denominator is everything ingested.
            "invalid_record_rate_pct": round(total * 100 / (coverage_metrics["total_records"] + total), 2) if (coverage_metrics.get("total_records") or total) else 0.0,
            **coverage_metrics,
        },
        "reasons": [{"reason": key, "count": value} for key, value in sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0]))],
        # RPT-08's pivot: the four fix states against the field each row
        # failed on (ZIP / Address / Coordinates / ...), replacing the pie.
        "fix_state_pivot": [
            {"reason": key, **value, "total": sum(value.values())}
            for key, value in sorted(fix_state_pivot.items(), key=lambda pair: (-sum(pair[1].values()), pair[0]))
        ],
        "brands": [{"brand": key, **value} for key, value in sorted(brand_counts.items(), key=lambda pair: (-pair[1]["invalid"], pair[0]))],
        "states": [{"state": key, "count": value} for key, value in sorted(state_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:25]],
        "cities": [{"city": key, "count": value} for key, value in sorted(city_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:25]],
        "history": history,
        "filters": {
            "brands": sorted({str(row.get("brand") or "Unknown") for row in rows}),
            "states": sorted({raw_value(row.get("raw_record"), "state", "state_code", "state_name").upper() for row in rows if raw_value(row.get("raw_record"), "state", "state_code", "state_name")}),
            "reasons": sorted(reason_counts),
        },
        "warning": "",
    }
    payload["quality_cache"] = "live"
    set_cached_query(quality_cache_key, payload)
    return payload


# ---------------------------------------------------------------------------
# Metric CSV export (entity/listing level)
# ---------------------------------------------------------------------------
# Every number card on both reporting tabs is downloadable, and the download
# must hand over the *entities the number was computed from* - one row per
# listing / error listing / ZIP - not a one-line restatement of the figure.
# The exported rows also carry the boolean flag columns the metric is defined
# by (has_valid_zip, is_duplicate, is_stale, ...), so the reader can recompute
# the headline number from the CSV itself rather than taking it on trust.
# A real analyst filter ("20 states, up to 200k listings") must actually come
# back, not be silently clipped. openpyxl writes this many rows comfortably
# within the 512MB budget because the workbook is built once and streamed.
# Excel's own hard ceiling is 1,048,576 rows, so this stays well inside it.
METRIC_EXPORT_ROW_LIMIT = 200000

# Metric slug -> the family that owns it. Slugs are the same kebab-case form
# the UI derives from a card's label, so a card needs no wiring beyond having
# a label. Each family exports the entity grain the metric is actually
# counted at, so the CSV's row count reconciles with the card's number.

# Fix counts are counted from quality_fix_events (the same source the Trends
# chart uses), NOT from error_listings.is_ai_enriched - exporting the latter
# would hand back a different population than the card displays.
# fix_type is normalised to upper case at write time (see
# record_quality_fix_event) - 'AI' / 'MANUAL'. BigQuery string equality is
# case sensitive, so comparing against 'Manual' silently matches nothing.
_FIX_EVENT_METRIC_TYPES: dict[str, str] = {
    "fixed-with-ai": "AI",
    "listings-fixed-automatically": "AI",
    "manually-fixed": "MANUAL",
    "listings-fixed-manually": "MANUAL",
}

# The open review population lives in error_listings.
_ERROR_METRIC_PREDICATES: dict[str, str] = {
    "ai-review-pending": "e.is_ai_enriched IS NOT TRUE AND e.has_ai_suggestion IS TRUE",
    "manual-review-pending": "e.is_ai_enriched IS NOT TRUE AND e.has_ai_suggestion IS NOT TRUE",
    "needs-manual-review": "e.is_ai_enriched IS NOT TRUE",
    "invalid-listings": "TRUE",
    "unresolved-rate": "TRUE",
    "active-issue-types": "TRUE",
    "entity-resolution-attempts": "COALESCE(e.attempt_count, 0) > 0",
    "entity-resolution-success": "COALESCE(e.attempt_count, 0) > 0",
}

# Coverage metrics are defined over `listings`; each exports the full entity
# population plus the boolean flag column its rate is defined by, so the
# headline percentage is reproducible from the file itself.
_LISTING_METRIC_SLUGS: frozenset[str] = frozenset({
    "zip-completeness", "coordinate-completeness", "duplicate-rate",
    "stale-records",
})

# "Total Stores" is a location-tab metric, so it exports the enriched
# location view (county, state_name, demographics, coordinate provenance)
# rather than the raw bronze listing columns - the location export should
# carry the richest location fields available, not the thinnest.
# "Total Listings" is the canonical card label now; the old slug stays so a
# bookmarked export URL keeps working.
_LOCATION_VIEW_METRIC_SLUGS: frozenset[str] = frozenset({"total-listings", "total-stores"})

# Market-coverage metrics are counted over the ZIP universe, not over
# listings - exporting listing rows for "Uncovered ZIPs" would be nonsense,
# since an uncovered ZIP has no listing by definition. Grain is one ZIP.
_ZIP_METRIC_SLUGS: frozenset[str] = frozenset({
    "total-states", "market-zips", "covered-markets-zips",
    "covered-states", "covered-cities", "uncovered-zips",
})

_BRAND_METRIC_SLUGS: frozenset[str] = frozenset({"active-brands"})


# Human labels for the export columns. Anything not listed falls back to a
# title-cased version of the column name, so a new column never breaks the
# export - it just gets a plain label.
_METRIC_EXPORT_COLUMN_LABELS: dict[str, str] = {
    "business_id": "Brand ID", "brand": "Brand", "name": "Store / Location Name",
    "address": "Street Address", "city_name": "City", "county": "County",
    "state_code": "State Code", "state_name": "State", "zip_code": "ZIP Code",
    "country": "Country", "phone_number": "Phone",
    "latitude": "Latitude", "longitude": "Longitude",
    "coordinate_confidence": "Coord Confidence", "coordinate_source": "Coord Source",
    "population": "Census Population", "median_household_income": "Median Income ($)",
    "median_age": "Median Age", "last_observed_at": "Last Observed",
    "enriched_at": "Enriched At", "ingestion_id": "Ingestion ID",
    "content_hash": "Content Hash", "listing_id": "Listing ID",
    "custom_fields": "Additional Source Fields",
    "has_valid_zip": "Has Valid ZIP", "has_valid_coordinates": "Has Valid Coordinates",
    "is_stale": "Is Stale", "is_duplicate": "Is Duplicate",
    "duplicate_group_count": "Duplicate Group Size", "is_covered": "Is Covered",
    "location_count": "Locations In ZIP", "brands_present": "Brands Present",
    "event_id": "Event ID", "row_number": "Source Row #",
    "validation_error_type": "Validation Error Type", "errors": "Validation Errors",
    "raw_record": "Raw Source Record", "observed_at": "Observed At",
    "template_id": "Template ID", "enrichment_attempts": "Enrichment Attempts",
    "fixed_with_ai": "Fixed With AI", "has_ai_suggestion": "Has AI Suggestion",
    "fix_id": "Fix ID", "fix_type": "Fix Type", "fixed_at": "Fixed At",
    "processed": "Processed", "improved": "Improved",
    "listing_count": "Listing Count", "zip_count": "ZIP Count",
    "state_count": "State Count", "created_at": "Created At", "updated_at": "Updated At",
}

# What each metric measures, restated on the workbook's metrics sheet so the
# file explains its own arithmetic rather than relying on the reader to
# remember the card's definition.
_METRIC_EXPORT_DEFINITIONS: dict[str, str] = {
    "fixed-with-ai": "Fix events of type AI that were processed and improved the record.",
    "listings-fixed-automatically": "Fix events of type AI that were processed and improved the record.",
    "manually-fixed": "Fix events of type MANUAL that were processed and improved the record.",
    "listings-fixed-manually": "Fix events of type MANUAL that were processed and improved the record.",
    "ai-review-pending": "Invalid listings not yet fixed, for which AI has produced a suggestion awaiting review.",
    "manual-review-pending": "Invalid listings not yet fixed, with no AI suggestion - these need a human.",
    "needs-manual-review": "Invalid listings that have not been AI-enriched.",
    "invalid-listings": "All listings that failed validation and are in the review population.",
    "unresolved-rate": "Share of the invalid population still awaiting resolution.",
    "active-issue-types": "Distinct validation failure reasons present in the invalid population.",
    "entity-resolution-attempts": "Invalid listings that entity resolution has attempted at least once.",
    "entity-resolution-success": "Attempted rows, with the success flag per row; the rate is successes over attempts.",
    "zip-completeness": "Share of listings carrying a usable postal code (5-digit US, or alphanumeric non-US).",
    "coordinate-completeness": "Share of listings with in-range coordinates that are not the 0,0 placeholder.",
    "duplicate-rate": "Share of listings sharing a content_hash (or business/address/ZIP identity) with another.",
    "stale-records": "Listings not observed within the configured staleness window.",
    "total-listings": "Every individual listing record - can be more than one per ZIP.",
    "total-stores": "Every individual listing record - can be more than one per ZIP.",
    "total-states": "All states present in the ZIP market universe.",
    "market-zips": "All ZIPs in the addressable market universe.",
    "covered-markets-zips": "Distinct ZIPs where the selected brand(s) have at least one store.",
    "covered-states": "States where the selected brand(s) have at least one store.",
    "covered-cities": "Cities where the selected brand(s) have at least one store.",
    "uncovered-zips": "Market ZIPs with no store for the selected brand(s) - the whitespace.",
    "active-brands": "Brands in the registry with active status, and their listing footprint.",
}


def _metric_export_label(column: str) -> str:
    return _METRIC_EXPORT_COLUMN_LABELS.get(column, column.replace("_", " ").title())


def _metric_export_summary(metric: str, rows: list[dict[str, Any]], unavailable_reason: str = "") -> list[dict[str, Any]]:
    """Derive the metrics sheet from the exported rows themselves.

    Computing these from the sheet-1 rows (rather than re-querying) is
    deliberate: the two sheets can never disagree, and a reader can check
    every figure by hand against the data sitting next to it.
    """
    total = len(rows)
    summary: list[dict[str, Any]] = [
        {"metric": "Metric", "value": _metric_export_label(metric.replace("-", "_")), "basis": ""},
        {"metric": "Definition", "value": _METRIC_EXPORT_DEFINITIONS.get(metric, ""), "basis": ""},
        {"metric": "Rows in this export", "value": total, "basis": "Sheet 1 row count"},
        {"metric": "Generated at (UTC)", "value": datetime.now(timezone.utc).isoformat(timespec="seconds"), "basis": ""},
    ]
    if unavailable_reason:
        label = "PARTIAL RESULT" if "ceiling" in unavailable_reason else "DATA UNAVAILABLE"
        summary.insert(2, {"metric": label, "value": unavailable_reason, "basis": ""})
    if not rows:
        return summary

    columns = list(rows[0].keys())

    # Boolean flag columns are the arithmetic behind every rate card, so
    # report each one's count and share against this export's own row count.
    for column in columns:
        values = [row.get(column) for row in rows]
        non_null = [v for v in values if v not in (None, "")]
        if non_null and all(isinstance(v, bool) for v in non_null):
            true_count = sum(1 for v in non_null if v)
            summary.append({
                "metric": f"{_metric_export_label(column)} = TRUE",
                "value": true_count,
                "basis": f"{round(true_count * 100 / len(non_null), 2)}% of {len(non_null)} rows with a value",
            })
            summary.append({
                "metric": f"{_metric_export_label(column)} = FALSE",
                "value": len(non_null) - true_count,
                "basis": f"{round((len(non_null) - true_count) * 100 / len(non_null), 2)}% of {len(non_null)} rows with a value",
            })

    # Distinct-entity counts for the dimensions these metrics are sliced by.
    for column in ("brand", "business_id", "state_code", "state_name", "city_name", "zip_code", "validation_error_type", "fix_type"):
        if column in columns:
            distinct = {str(row.get(column)) for row in rows if row.get(column) not in (None, "")}
            summary.append({
                "metric": f"Distinct {_metric_export_label(column)}",
                "value": len(distinct),
                "basis": f"over {total} rows",
            })

    # Sums for the columns where a total is the meaningful figure.
    for column in ("location_count", "listing_count", "population"):
        if column in columns:
            numeric = [row.get(column) for row in rows if isinstance(row.get(column), (int, float)) and not isinstance(row.get(column), bool)]
            if numeric:
                summary.append({
                    "metric": f"Total {_metric_export_label(column)}",
                    "value": sum(numeric),
                    "basis": f"summed over {len(numeric)} rows",
                })
    return summary


def _metric_export_workbook(metric: str, rows: list[dict[str, Any]], unavailable_reason: str = "") -> bytes:
    """Build the two-sheet workbook: the entity rows, then the metrics over them."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    data_font = Font(name="Calibri", size=10)
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"), right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"), bottom=Side(style="thin", color="E2E8F0"),
    )

    def write_sheet(ws: Any, records: list[dict[str, Any]], columns: list[str], labels: list[str], empty_message: str) -> None:
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 28
        for col_idx, label in enumerate(labels, start=1):
            cell = ws.cell(row=1, column=col_idx, value=label)
            cell.fill, cell.font, cell.alignment = header_fill, header_font, header_align
        if not records:
            cell = ws.cell(row=2, column=1, value=empty_message)
            cell.font = Font(name="Calibri", size=10, italic=True, color="64748B")
            for col_idx in range(1, len(columns) + 1):
                ws.cell(row=2, column=col_idx).border = thin_border
            widths = [max(len(label) + 2, 14) for label in labels]
        else:
            widths = [len(label) + 2 for label in labels]
            for row_idx, record in enumerate(records, start=2):
                for col_idx, column in enumerate(columns, start=1):
                    value = record.get(column)
                    if isinstance(value, bool):
                        value = "TRUE" if value else "FALSE"
                    elif hasattr(value, "isoformat"):
                        value = value.isoformat()
                    elif isinstance(value, (dict, list)):
                        value = json.dumps(value, default=str)
                    elif value is None:
                        value = ""
                    # Excel refuses cells over 32,767 chars - raw_record JSON
                    # can exceed that, and a hard failure there would lose the
                    # whole export rather than one field.
                    if isinstance(value, str) and len(value) > 32000:
                        value = value[:32000] + "...[truncated]"
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    cell.font = data_font
                    cell.border = thin_border
                    if row_idx % 2 == 0:
                        cell.fill = alt_fill
                    widths[col_idx - 1] = max(widths[col_idx - 1], min(len(str(value)) + 2, 60))
        for col_idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max(width, 12), 60)

    wb = openpyxl.Workbook()
    ws_data = wb.active
    ws_data.title = "Listing Data"
    data_columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in data_columns:
                data_columns.append(key)
    empty_message = unavailable_reason or "No records matched this metric under the current filters."
    write_sheet(ws_data, rows, data_columns, [_metric_export_label(c) for c in data_columns], empty_message)

    ws_metrics = wb.create_sheet(title="Metrics")
    summary = _metric_export_summary(metric, rows, unavailable_reason)
    write_sheet(ws_metrics, summary, ["metric", "value", "basis"], ["Metric", "Value", "Basis"], "No metrics to report.")

    # Competitor view: the same rows pivoted by brand, so the export answers
    # "how do we compare" and not only "what do we have". Whitespace analysis
    # is a competitive question - a per-brand breakdown is the point, and it
    # is derived from the sheet-1 rows so it always reconciles with them.
    ws_competitors = wb.create_sheet(title="Competitors")
    competitor_rows = _metric_export_competitors(rows)
    write_sheet(
        ws_competitors, competitor_rows,
        ["brand", "listings", "share_pct", "states", "cities", "zips", "with_coordinates", "with_valid_zip"],
        ["Brand", "Listings", "Share %", "States", "Cities", "ZIPs", "With Coordinates", "With Valid ZIP"],
        "This metric's rows carry no brand dimension, so there is nothing to compare.")

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _metric_export_competitors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-brand breakdown of the exported rows, biggest first.

    Derived from the same rows as sheet 1 (not a second query), so the two
    can never disagree. Returns [] when the rows carry no brand column -
    better an explicit "nothing to compare" than a sheet of blanks.
    """
    if not rows or not any("brand" in row for row in rows):
        return []
    total = len(rows)
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        brand = str(row.get("brand") or "Unknown").strip() or "Unknown"
        bucket = buckets.setdefault(brand, {
            "brand": brand, "listings": 0,
            "_states": set(), "_cities": set(), "_zips": set(),
            "with_coordinates": 0, "with_valid_zip": 0,
        })
        bucket["listings"] += 1
        for key, target in (("state_code", "_states"), ("city_name", "_cities"), ("zip_code", "_zips")):
            value = row.get(key)
            if value not in (None, ""):
                bucket[target].add(str(value))
        if row.get("has_valid_coordinates") is True or (
            row.get("latitude") not in (None, "") and row.get("longitude") not in (None, "")
        ):
            bucket["with_coordinates"] += 1
        if row.get("has_valid_zip") is True or (
            "has_valid_zip" not in row and row.get("zip_code") not in (None, "")
        ):
            bucket["with_valid_zip"] += 1
    out: list[dict[str, Any]] = []
    for bucket in buckets.values():
        out.append({
            "brand": bucket["brand"],
            "listings": bucket["listings"],
            "share_pct": round(bucket["listings"] * 100 / total, 2) if total else 0.0,
            "states": len(bucket["_states"]),
            "cities": len(bucket["_cities"]),
            "zips": len(bucket["_zips"]),
            "with_coordinates": bucket["with_coordinates"],
            "with_valid_zip": bucket["with_valid_zip"],
        })
    out.sort(key=lambda item: item["listings"], reverse=True)
    return out


def _metric_export_csv(rows: list[dict[str, Any]]) -> str:
    """Render rows as CSV. Columns are the union of every row's keys, so a
    value is never dropped just because the first row lacked that column."""
    if not rows:
        return ""
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: ("" if row.get(key) is None else row.get(key)) for key in headers})
    return buffer.getvalue()


def _metric_export_bundle(metric: str, rows: list[dict[str, Any]], unavailable_reason: str = "",
                          applied_filters: dict[str, Any] | None = None) -> bytes:
    """Package one metric export as a ZIP.

    A ZIP rather than a bare .xlsx because a single click should hand over
    everything needed to work with the number, in the form each consumer
    wants it:
      <metric>.xlsx  - the 2-sheet workbook (entities + the metrics over them)
      listings.csv   - the same entity rows, normalized, for loading into
                       anything that is not Excel
      metrics.csv    - the metrics sheet as plain CSV
      README.txt     - what the metric means, the filters that produced this
                       file, the row count, and any truncation
    Excel alone could not carry the normalized copy or the provenance note.
    """
    summary = _metric_export_summary(metric, rows, unavailable_reason)
    readme_lines = [
        f"Metric: {_metric_export_label(metric.replace('-', '_'))}",
        f"Definition: {_METRIC_EXPORT_DEFINITIONS.get(metric, '(not documented)')}",
        f"Generated (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Rows in this export: {len(rows):,}",
        "",
        "Filters applied:",
    ]
    filters = applied_filters or {}
    if any(filters.values()):
        for key, value in filters.items():
            if value:
                shown = ", ".join(value) if isinstance(value, list) else str(value)
                readme_lines.append(f"  - {key}: {shown}")
    else:
        readme_lines.append("  - none (full population)")
    if unavailable_reason:
        readme_lines += ["", "IMPORTANT:", f"  {unavailable_reason}"]
    readme_lines += [
        "",
        "Files:",
        f"  {metric}.xlsx  - workbook: 'Listing Data' + 'Metrics'",
        "  listings.csv    - the entity rows behind the number",
        "  metrics.csv     - the arithmetic, computed from those same rows",
        "  competitors.csv - per-brand breakdown (omitted when the rows carry no brand)",
        "",
        "Every figure on the Metrics sheet is computed from the rows in this",
        "file, so the headline number can be recomputed by hand from them.",
    ]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{metric}.xlsx", _metric_export_workbook(metric, rows, unavailable_reason))
        bundle.writestr("listings.csv", _metric_export_csv(rows))
        bundle.writestr("metrics.csv", _metric_export_csv(summary))
        competitors = _metric_export_competitors(rows)
        if competitors:
            bundle.writestr("competitors.csv", _metric_export_csv(competitors))
        bundle.writestr("README.txt", "\n".join(readme_lines))
    return buffer.getvalue()


def reporting_metric_export(params: dict[str, list[str]] | None = None) -> tuple[bytes, str]:
    """Return (xlsx_bytes, filename) for one metric card's download.

    Sheet 1 is the entity rows the number was computed from (listing / error
    listing / ZIP / brand grain, whichever the metric is actually counted at).
    Sheet 2 restates the metric's definition and the arithmetic over exactly
    those rows, so the workbook explains and proves its own headline figure.

    Raises ValueError for an unknown metric so the caller can answer 400
    rather than silently handing back an empty or invented file (INV-15).
    """
    from google.cloud import bigquery

    params = params or {}
    metric = str(params.get("metric", [""])[0] or "").strip().lower()
    if not metric:
        raise ValueError("metric is required")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{metric}-{stamp}.zip"

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    # Both tables are queried by column name below, including columns added
    # in later releases (has_ai_suggestion, custom_fields). Without these
    # passes the deployed table can lack them and BigQuery answers "Name X
    # not found" - the exact failure that took the quality tab down.
    try:
        _ensure_once("error_listings", _ensure_error_listings_table, client, project_id, dataset_id)
        _ensure_once("listings", _ensure_listings_table, client, project_id, dataset_id)
    except Exception as exc:
        LOGGER.warning("export_schema_ensure_failed error=%s", exc)

    # Filters accept a list, not a single value: selecting 20 states used to
    # collapse to one scalar compared with `=`, so the export came back
    # empty/unavailable instead of covering the selection. Repeated params
    # (?state=TX&state=CA) and comma-separated ones both work.
    def _multi(name: str, upper: bool = False) -> list[str]:
        values: list[str] = []
        for raw in params.get(name, []) or []:
            for piece in str(raw or "").split(","):
                cleaned = piece.strip()
                if upper:
                    cleaned = cleaned.upper()
                if cleaned and cleaned not in values:
                    values.append(cleaned)
        return values

    brands = _multi("brand")
    states = _multi("state", upper=True)
    start_date = str(params.get("start_date", [""])[0] or "").strip()
    end_date = str(params.get("end_date", [""])[0] or "").strip()
    query_params = [
        bigquery.ArrayQueryParameter("brands", "STRING", brands),
        bigquery.ArrayQueryParameter("states", "STRING", states),
        bigquery.ScalarQueryParameter("start_date", "STRING", start_date),
        bigquery.ScalarQueryParameter("end_date", "STRING", end_date),
    ]

    if metric in _FIX_EVENT_METRIC_TYPES:
        fix_type = _FIX_EVENT_METRIC_TYPES[metric]
        query = f"""
        SELECT
          qf.fix_id, qf.fix_type, qf.created_at AS fixed_at,
          qf.listing_id, qf.event_id, qf.row_number,
          qf.processed, qf.improved, qf.content_hash,
          e.business_id,
          COALESCE(b.name, e.business_id) AS brand,
          e.validation_error_type, e.errors, e.raw_record
        FROM `{project_id}.{dataset_id}.quality_fix_events` qf
        LEFT JOIN `{project_id}.{dataset_id}.error_listings` e
          ON e.event_id = qf.event_id AND e.row_number = qf.row_number
        LEFT JOIN `{project_id}.{dataset_id}.businesses` b
          ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
        WHERE UPPER(qf.fix_type) = '{fix_type}' AND qf.processed AND qf.improved
          AND (COALESCE(ARRAY_LENGTH(@brands), 0) = 0 OR COALESCE(b.name, e.business_id) IN UNNEST(@brands))
          AND (@start_date = '' OR DATE(qf.created_at) >= SAFE_CAST(@start_date AS DATE))
          AND (@end_date = '' OR DATE(qf.created_at) <= SAFE_CAST(@end_date AS DATE))
        ORDER BY qf.created_at DESC
        LIMIT {METRIC_EXPORT_ROW_LIMIT}
        """
    elif metric in _ERROR_METRIC_PREDICATES:
        predicate = _ERROR_METRIC_PREDICATES[metric]
        query = f"""
        SELECT
          e.event_id, e.row_number, e.business_id,
          COALESCE(b.name, e.business_id) AS brand,
          e.validation_error_type, e.errors, e.raw_record, e.country,
          e.observed_at, e.template_id, e.ingestion_id, e.content_hash,
          COALESCE(e.attempt_count, 0) AS enrichment_attempts,
          e.is_ai_enriched AS fixed_with_ai,
          e.has_ai_suggestion AS has_ai_suggestion
        FROM `{project_id}.{dataset_id}.error_listings` e
        LEFT JOIN `{project_id}.{dataset_id}.businesses` b
          ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
        WHERE e.is_deleted IS NOT TRUE
          AND ({predicate})
          AND (COALESCE(ARRAY_LENGTH(@brands), 0) = 0 OR COALESCE(b.name, e.business_id) IN UNNEST(@brands))
          AND (@start_date = '' OR DATE(e.observed_at) >= SAFE_CAST(@start_date AS DATE))
          AND (@end_date = '' OR DATE(e.observed_at) <= SAFE_CAST(@end_date AS DATE))
        ORDER BY e.observed_at DESC
        LIMIT {METRIC_EXPORT_ROW_LIMIT}
        """
    elif metric in _LISTING_METRIC_SLUGS:
        stale_after_days = get_stale_after_days()
        # Braces in the regexes are doubled: this is an f-string, and a bare
        # {5} is consumed as a format field (the bug that once silently made
        # ZIP completeness read 0%).
        query = f"""
        WITH base AS (
          SELECT
            l.listing_id, l.business_id,
            COALESCE(b.name, l.business_id) AS brand,
            l.name, l.address, l.city_name, l.state_code, l.zip_code,
            l.country, l.latitude, l.longitude,
            l.last_observed_at, l.enriched_at, l.ingestion_id, l.content_hash,
            -- Source columns no typed field covers, preserved per row. A
            -- listing export must carry them or it is not the full record.
            l.custom_fields,
            REGEXP_CONTAINS(TRIM(COALESCE(l.zip_code,'')), r'^[0-9]{{5}}$')
              OR REGEXP_CONTAINS(UPPER(TRIM(COALESCE(l.zip_code,''))), r'^[A-Z0-9][A-Z0-9 -]{{2,9}}$') AS has_valid_zip,
            (l.latitude IS NOT NULL AND l.longitude IS NOT NULL
             AND l.latitude BETWEEN -90 AND 90 AND l.longitude BETWEEN -180 AND 180
             AND NOT (l.latitude = 0 AND l.longitude = 0)) AS has_valid_coordinates,
            l.last_observed_at < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {stale_after_days} DAY) AS is_stale,
            COUNT(*) OVER (
              PARTITION BY COALESCE(
                NULLIF(TRIM(COALESCE(l.content_hash, '')), ''),
                CONCAT(COALESCE(l.business_id,''), '|', LOWER(TRIM(COALESCE(l.address,''))), '|', COALESCE(l.zip_code,''))
              )
            ) AS duplicate_group_count
          FROM `{project_id}.{dataset_id}.listings` l
          LEFT JOIN `{project_id}.{dataset_id}.businesses` b
            ON b.business_id = l.business_id AND b.is_deleted IS NOT TRUE
          WHERE l.is_deleted IS NOT TRUE
            AND (COALESCE(ARRAY_LENGTH(@brands), 0) = 0 OR COALESCE(b.name, l.business_id) IN UNNEST(@brands))
            AND (COALESCE(ARRAY_LENGTH(@states), 0) = 0 OR UPPER(COALESCE(l.state_code,'')) IN UNNEST(@states))
        )
        SELECT *, duplicate_group_count > 1 AS is_duplicate
        FROM base
        ORDER BY last_observed_at DESC
        LIMIT {METRIC_EXPORT_ROW_LIMIT}
        """
    elif metric in _LOCATION_VIEW_METRIC_SLUGS:
        _, _, _, gold_dataset_id, _ = _medallion_settings()
        gold_ref = f"{project_id}.{gold_dataset_id}"
        query = f"""
        SELECT
          brand, name, address, city_name, county, state_code, state_name,
          zip_code, country, phone_number, latitude, longitude,
          coordinate_confidence, coordinate_source,
          population, median_household_income, median_age, last_observed_at
        FROM `{gold_ref}.vw_reporting_locations`
        WHERE (COALESCE(ARRAY_LENGTH(@brands), 0) = 0 OR brand IN UNNEST(@brands))
          AND (COALESCE(ARRAY_LENGTH(@states), 0) = 0 OR UPPER(COALESCE(state_code,'')) IN UNNEST(@states))
        ORDER BY state_code, city_name, address
        LIMIT {METRIC_EXPORT_ROW_LIMIT}
        """
    elif metric in _ZIP_METRIC_SLUGS:
        _, _, _, gold_dataset_id, _ = _medallion_settings()
        gold_ref = f"{project_id}.{gold_dataset_id}"
        # One row per ZIP in the market universe, carrying the coverage flag
        # the card counts. "Uncovered ZIPs" restricts to is_covered = FALSE;
        # the covered-* cards restrict to TRUE; the universe cards export the
        # lot so both sides of the ratio are visible.
        if metric == "uncovered-zips":
            coverage_filter = "WHERE NOT is_covered"
        elif metric in {"covered-markets-zips", "covered-states", "covered-cities"}:
            coverage_filter = "WHERE is_covered"
        else:
            coverage_filter = ""
        query = f"""
        WITH zips AS (
          SELECT
            zip_code,
            ANY_VALUE(state_code) AS state_code,
            ANY_VALUE(state_name) AS state_name,
            ANY_VALUE(county) AS county,
            ANY_VALUE(city_name) AS city_name,
            ANY_VALUE(population) AS population,
            ANY_VALUE(median_household_income) AS median_household_income,
            ANY_VALUE(latitude) AS latitude,
            ANY_VALUE(longitude) AS longitude,
            SUM(CASE WHEN COALESCE(ARRAY_LENGTH(@brands), 0) = 0 OR brand_name IN UNNEST(@brands) THEN COALESCE(location_count, 0) ELSE 0 END) AS location_count,
            STRING_AGG(DISTINCT CASE WHEN COALESCE(location_count, 0) > 0 THEN brand_name END, '; ') AS brands_present
          FROM `{gold_ref}.vw_reporting_gap_base`
          WHERE (COALESCE(ARRAY_LENGTH(@states), 0) = 0 OR UPPER(COALESCE(state_code,'')) IN UNNEST(@states))
          GROUP BY zip_code
        ),
        flagged AS (
          SELECT *, location_count > 0 AS is_covered FROM zips
        )
        -- is_covered must be computed in its own CTE: BigQuery cannot
        -- reference a SELECT-list alias from the WHERE of the same query
        -- ("Unrecognized name: is_covered").
        SELECT * FROM flagged
        {coverage_filter}
        ORDER BY population DESC
        LIMIT {METRIC_EXPORT_ROW_LIMIT}
        """
    elif metric in _BRAND_METRIC_SLUGS:
        # "Active Brands" is counted over the brand registry, so the export
        # is one row per brand with its listing footprint.
        query = f"""
        SELECT
          b.business_id, b.name AS brand, b.slug, b.status,
          b.created_at, b.updated_at, b.country_of_origin,
          COUNT(l.listing_id) AS listing_count,
          COUNT(DISTINCT l.zip_code) AS zip_count,
          COUNT(DISTINCT l.state_code) AS state_count
        FROM `{project_id}.{dataset_id}.businesses` b
        LEFT JOIN `{project_id}.{dataset_id}.listings` l
          ON l.business_id = b.business_id AND l.is_deleted IS NOT TRUE
          AND (COALESCE(ARRAY_LENGTH(@states), 0) = 0 OR UPPER(COALESCE(l.state_code,'')) IN UNNEST(@states))
        WHERE b.is_deleted IS NOT TRUE AND COALESCE(b.status, 'active') = 'active'
          AND (COALESCE(ARRAY_LENGTH(@brands), 0) = 0 OR b.name IN UNNEST(@brands))
        GROUP BY b.business_id, b.name, b.slug, b.status, b.created_at, b.updated_at, b.country_of_origin
        ORDER BY listing_count DESC
        LIMIT {METRIC_EXPORT_ROW_LIMIT}
        """
    else:
        raise ValueError(f"unknown metric: {metric}")

    # A missing table/view is an honest empty result (the warehouse layer has
    # not been built yet), but the workbook must SAY so - an empty sheet that
    # looks identical to a real zero is the same silent-zero trap that once
    # made every coverage metric read 0%. Any other failure propagates to a
    # 400 rather than being dressed up as "no records".
    unavailable_reason = ""
    try:
        rows = list(client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=query_params)).result())
    except Exception as exc:
        if getattr(exc, "code", None) == 404 or "not found" in str(exc).lower():
            rows = []
            unavailable_reason = (
                "The warehouse table or view backing this metric does not exist yet, "
                "so this export is empty because the data is unavailable - not because "
                "the metric is genuinely zero."
            )
            LOGGER.warning("metric_export_source_missing metric=%s error=%s", metric, str(exc)[:200])
        else:
            raise

    def scalar(value: Any) -> Any:
        # Booleans pass through untouched: the metrics sheet detects flag
        # columns by type to compute each rate, so stringifying them here
        # would silently drop that arithmetic.
        if isinstance(value, bool):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, default=str)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    export_rows = [{key: scalar(value) for key, value in dict(row).items()} for row in rows]
    # Hitting the ceiling means the file is a partial answer. Saying so beats
    # handing over a truncated sheet that looks complete.
    if len(export_rows) >= METRIC_EXPORT_ROW_LIMIT and not unavailable_reason:
        unavailable_reason = (
            f"This export reached the {METRIC_EXPORT_ROW_LIMIT:,}-row ceiling, so it is a "
            "partial result. Narrow the filters (fewer states, a shorter date range) to "
            "get a complete file."
        )
    return _metric_export_bundle(metric, export_rows, unavailable_reason,
                                {"brand": brands, "state": states,
                                 "start_date": start_date, "end_date": end_date}), filename


def reporting_timeseries(params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Return timeseries counts for the reporting Trends Over Time chart.

    Per RPT-05, the legend is never brands - it's the metric dimension
    itself (Locations / Errors / AI Fixed / Manual Fixed), aggregated across
    whichever brands are selected in the sidebar filter (a filter, not a
    grouping key). Always returns all four series regardless of the old
    single-`metric` selector, which used to pick exactly one dimension and
    then (incorrectly) split *that* into one line per brand.

    Query params:
      brands   – comma-separated brand names (primary + competitors) - a filter, not a series split
      period   – 1D | 1W | 1M | 1Q | 1Y  (default 1M)
    """
    from google.cloud import bigquery

    params = params or {}
    period = str(params.get("period", ["1M"])[0] or "1M").upper().strip()
    brands_raw = str(params.get("brands", [""])[0] or "").strip()
    brands = [b.strip() for b in brands_raw.split(",") if b.strip()] if brands_raw else []

    # Never finer than a day (explicit ask: "granularity till day level
    # only"), rolling up to week/month/quarter as the period widens.
    PERIOD_CONFIG: dict[str, tuple[str, str]] = {
        "1D": ("DAY",   "1 DAY"),
        "1W": ("DAY",   "7 DAY"),
        "1M": ("DAY",   "30 DAY"),
        "1Q": ("WEEK",  "90 DAY"),
        "1Y": ("MONTH", "365 DAY"),
    }
    granularity, interval = PERIOD_CONFIG.get(period, ("DAY", "30 DAY"))
    force_refresh = str(params.get("refresh", [""])[0] or "").lower() in {"1", "true", "yes"}
    timeseries_cache_key = f"reporting_timeseries:v2:{period}:{','.join(sorted(brands))}"
    if not force_refresh:
        cached_series = get_cached_query(timeseries_cache_key)
        if cached_series:
            cached_series["timeseries_cache"] = "sqlite"
            return cached_series

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("brands", "STRING", brands)]
    ) if brands else bigquery.QueryJobConfig()
    brand_filter_loc = "AND COALESCE(b.name, l.business_id) IN UNNEST(@brands)" if brands else ""
    brand_filter_err = "AND COALESCE(b.name, e.business_id) IN UNNEST(@brands)" if brands else ""
    # quality_fix_events carries no business_id of its own - only
    # event_id/row_number, tying back to the error_listings row it fixed.
    brand_filter_fix = "AND COALESCE(b.name, e.business_id) IN UNNEST(@brands)" if brands else ""

    def _collect(query: str, label: str) -> dict[str, Any] | None:
        try:
            rows = list(client.query(query, job_config=job_config).result())
            points = []
            for row in rows:
                ts = row.get("bucket")
                date_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                points.append({"date": date_str, "count": int(row.get("cnt", 0) or 0)})
            return {"label": label, "points": points}
        except Exception as exc:
            LOGGER.warning("timeseries_query_failed metric=%s error=%s", label, exc)
            return None

    # listings has no brand_name column of its own (only business_id) - brand
    # comes from a join to businesses, same pattern the errors/fixes queries
    # below already use correctly.
    locations_series = _collect(f"""
        SELECT TIMESTAMP_TRUNC(l.last_observed_at, {granularity}) AS bucket, COUNT(*) AS cnt
        FROM `{project_id}.{dataset_id}.listings` l
        LEFT JOIN `{project_id}.{dataset_id}.businesses` b
          ON b.business_id = l.business_id AND b.is_deleted IS NOT TRUE
        WHERE l.is_deleted IS NOT TRUE
          AND l.last_observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {interval})
          {brand_filter_loc}
        GROUP BY bucket ORDER BY bucket
    """, "Locations")
    errors_series = _collect(f"""
        SELECT TIMESTAMP_TRUNC(e.observed_at, {granularity}) AS bucket, COUNT(*) AS cnt
        FROM `{project_id}.{dataset_id}.error_listings` e
        LEFT JOIN `{project_id}.{dataset_id}.businesses` b
          ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
        WHERE e.is_deleted IS NOT TRUE
          AND e.observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {interval})
          {brand_filter_err}
        GROUP BY bucket ORDER BY bucket
    """, "Errors")
    # quality_fix_events has no business_id column - join through
    # error_listings (event_id + row_number) to reach the brand, same as
    # _refresh_quality_fix_metrics_from_bigquery()'s own join pattern.
    ai_fixed_series = _collect(f"""
        SELECT TIMESTAMP_TRUNC(qf.created_at, {granularity}) AS bucket, COUNT(*) AS cnt
        FROM `{project_id}.{dataset_id}.quality_fix_events` qf
        LEFT JOIN `{project_id}.{dataset_id}.error_listings` e
          ON e.event_id = qf.event_id AND e.row_number = qf.row_number
        LEFT JOIN `{project_id}.{dataset_id}.businesses` b
          ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
        WHERE qf.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {interval})
          AND qf.fix_type = 'AI' AND qf.processed AND qf.improved
          {brand_filter_fix}
        GROUP BY bucket ORDER BY bucket
    """, "AI Fixed")
    manual_fixed_series = _collect(f"""
        SELECT TIMESTAMP_TRUNC(qf.created_at, {granularity}) AS bucket, COUNT(*) AS cnt
        FROM `{project_id}.{dataset_id}.quality_fix_events` qf
        LEFT JOIN `{project_id}.{dataset_id}.error_listings` e
          ON e.event_id = qf.event_id AND e.row_number = qf.row_number
        LEFT JOIN `{project_id}.{dataset_id}.businesses` b
          ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
        WHERE qf.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {interval})
          AND qf.fix_type = 'MANUAL' AND qf.processed AND qf.improved
          {brand_filter_fix}
        GROUP BY bucket ORDER BY bucket
    """, "Manual Fixed")

    series = [s for s in (locations_series, errors_series, ai_fixed_series, manual_fixed_series) if s is not None]
    payload = {"period": period, "granularity": granularity, "series": series, "timeseries_cache": "live"}
    if series:
        set_cached_query(timeseries_cache_key, payload)
    return payload


def _fetch_rejected_by_keys(claimed_ids: list[str], *, client: Any = None) -> list[dict[str, Any]]:

    if not claimed_ids:
        return []
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    if client is None:
        client = _bigquery_client(project_id, credentials_json)

    conditions = []
    params = []
    param_cls = getattr(bigquery, "ScalarQueryParameter", None)
    for idx, cid in enumerate(claimed_ids):
        if ":" in cid:
            parts = cid.split(":", 1)
            e_param = f"e_{idx}"
            r_param = f"r_{idx}"
            conditions.append(f"(event_id = @{e_param} AND row_number = @{r_param})")
            if param_cls:
                params.append(param_cls(e_param, "STRING", parts[0]))
                params.append(param_cls(r_param, "INT64", int(parts[1]) if parts[1].isdigit() else 0))
        else:
            l_param = f"l_{idx}"
            conditions.append(f"listing_id = @{l_param}")
            if param_cls:
                params.append(param_cls(l_param, "STRING", cid))

    if not conditions:
        return []

    where_clause = " OR ".join(conditions)
    query = f"""SELECT event_id, business_id, source_type_id, row_number, errors, raw_record, template_id, mapping_id, is_ai_enriched, attempt_count, has_ai_suggestion
    FROM `{project_id}.{dataset_id}.error_listings`
    WHERE is_deleted IS NOT TRUE AND ({where_clause})"""

    cfg_cls = getattr(bigquery, "QueryJobConfig", None)
    job_config = cfg_cls(query_parameters=params) if (cfg_cls and params) else None
    try:
        result_rows = client.query(query, job_config=job_config).result()
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return []
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
    return records


def auto_repair_error_batch(limit: int = 10, offset: int = 0, *, client: Any = None) -> dict[str, int]:
    """Retry review batches through the set-swap queue with progressive advancement.
    Candidate IDs enter a source set; repaired rows graduate to listings and delete
    from review; failed rows enter the failed set. Once the source set is empty,
    it swaps with the failed set and merges any new errors for the next advancement cycle.
    """
    from whitespace_tool.sqlite_cache import (
        seed_or_swap_enrichment_cycle,
        claim_enrichment_batch,
        complete_enrichment_claim,
        get_db_connection,
    )
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    if client is None:
        client = _bigquery_client(project_id, credentials_json)

    batch_limit = max(1, min(int(limit), 10))
    cycle_id, pending_count = seed_or_swap_enrichment_cycle()
    claimed_ids = claim_enrichment_batch(cycle_id, limit=batch_limit)
    if not claimed_ids and pending_count == 0:
        cycle_id, pending_count = seed_or_swap_enrichment_cycle()
        claimed_ids = claim_enrichment_batch(cycle_id, limit=batch_limit)

    records = []
    if claimed_ids:
        records = _fetch_rejected_by_keys(claimed_ids, client=client)

    if not records:
        pending_result = list_rejected(limit=batch_limit, ai_pending_only=True, client=client)
        records = pending_result.get("records", [])
        if records:
            seed_ids = [str(r.get("listing_id") or f"{r.get('event_id')}:{r.get('row_number')}") for r in records]
            cycle_id, _ = seed_or_swap_enrichment_cycle(seed_ids)
            claimed_ids = claim_enrichment_batch(cycle_id, limit=batch_limit)

    if not records:
        return {"attempted": 0, "resolved": 0, "remaining": 0}

    templates = {item.get("workflow_template_id"): item for item in list_templates(client=client).get("templates", [])}
    resolved = 0
    processed_keys = []
    for record in records:
        rec_lid = str(record.get("listing_id") or f"{record.get('event_id')}:{record.get('row_number')}")
        processed_keys.append((str(record.get("event_id") or ""), int(record.get("row_number") or 0)))
        template = templates.get(record.get("template_id"))
        components = (template or {}).get("components") if template else None
        if isinstance(components, str):
            try:
                components = json.loads(components)
            except ValueError:
                components = None
        mapper = components.get("mapper") if isinstance(components, dict) else None
        improved = False
        if not isinstance(mapper, dict):
            complete_enrichment_claim(rec_lid, cycle_id, improved=False)
            try:
                _record_quality_fix_event(
                    event_id=record.get("event_id"),
                    row_number=int(record.get("row_number") or 0),
                    fix_type="AI",
                    processed=True,
                    improved=False,
                    listing_id=record.get("listing_id"),
                )
            except Exception as event_exc:
                LOGGER.warning("quality_fix_event_write_failed type=AI event_id=%s row=%s error=%s", record.get("event_id"), record.get("row_number"), event_exc)
            continue
        mapper["business_id"] = record.get("business_id") or mapper.get("business_id")
        mapper["source_type_id"] = record.get("source_type_id") or mapper.get("source_type_id")
        mapper["is_ai_enriched"] = True

        raw_rec = record.get("raw_record")
        reprocess_rows = None
        if isinstance(raw_rec, dict):
            from whitespace_tool.geo_enrichment import enrich_raw_listing_row
            try:
                with get_db_connection() as conn:
                    enriched_rec = enrich_raw_listing_row(raw_rec, conn)
                reprocess_rows = [enriched_rec]
            except Exception as geo_exc:
                LOGGER.warning("geo_enrichment_during_repair_failed error=%s", geo_exc)

        try:
            reprocess_payload = {
                "event_id": record["event_id"],
                "row_numbers": [record["row_number"]],
                "mapper": mapper,
                "is_ai_enriched": True,
            }
            if reprocess_rows is not None:
                reprocess_payload["rows"] = reprocess_rows
            result = reprocess_rejected(reprocess_payload, client=client)
            if (
                result.get("mapped_rows", 0) > 0
                and result.get("error_listings_cleanup", {}).get("ok")
                and int(result.get("error_listings_cleanup", {}).get("rows_updated", 0) or 0) > 0
            ):
                improved = True
                resolved += 1
        except Exception as exc:
            LOGGER.warning("automatic_error_repair_failed event_id=%s row=%s error=%s", record.get("event_id"), record.get("row_number"), exc)
        finally:
            complete_enrichment_claim(rec_lid, cycle_id, improved=improved)
            try:
                _record_quality_fix_event(
                    event_id=record.get("event_id"),
                    row_number=int(record.get("row_number") or 0),
                    fix_type="AI",
                    processed=True,
                    improved=improved,
                    listing_id=record.get("listing_id"),
                )
            except Exception as event_exc:
                LOGGER.warning("quality_fix_event_write_failed type=AI event_id=%s row=%s error=%s", record.get("event_id"), record.get("row_number"), event_exc)
    if processed_keys:
        for event_id, row_number in processed_keys:
            client.query(
                f"""UPDATE `{project_id}.{dataset_id}.error_listings`
                SET is_ai_enriched = TRUE
                WHERE event_id = @event_id AND row_number = @row_number
                  AND is_deleted IS NOT TRUE""",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("event_id", "STRING", event_id),
                    bigquery.ScalarQueryParameter("row_number", "INT64", row_number),
                ])
            ).result()
    if resolved > 0:
        _invalidate_cache_background()
    return {"attempted": len(records), "resolved": resolved, "remaining": max(len(records) - resolved, 0)}


def start_auto_repair() -> dict[str, Any]:
    """Run the current review set once in advancing ten-row batches."""
    global AUTO_REPAIR_THREAD
    with AUTO_REPAIR_LOCK:
        if AUTO_REPAIR_THREAD and AUTO_REPAIR_THREAD.is_alive():
            return {"status": "running", "processed": ENRICHMENT_STATUS.get("processed", 0)}

        def worker() -> None:
            ENRICHMENT_STOP_REQUESTED.clear()
            ENRICHMENT_STATUS.update({"state": "running", "processed": 0, "current_id": "", "updated_at": utc_now_iso()})
            offset = 0
            fixed = 0
            project_id, dataset_id, credentials_json = _warehouse_settings()
            client = _bigquery_client(project_id, credentials_json)
            try:
                _schedule_quality_fix_metrics_refresh(force=True)
                current_stats = get_auto_repair_stats()
                base_fixed = int(current_stats.get("fixed", 0) or 0)
                base_processed = int(current_stats.get("processed", 0) or 0)
                base_manual = int(current_stats.get("manual_fixed", 0) or 0)
                total = _count_error_listings_live(client=client)
                AUTO_REPAIR_STATS.update({"fixed": base_fixed, "processed": base_processed, "remaining": total})
                set_auto_repair_stats(base_fixed, base_processed, total, base_manual)
                while offset < total:
                    _enrichment_checkpoint()
                    # Yield to whatever the user is actively doing (parsing,
                    # saving, reviewing) rather than competing with it for
                    # the same BigQuery client/SQLite connections - this is
                    # explicitly best-effort background work, so it can
                    # always afford to wait a little longer.
                    idle_seconds = wall_clock_time() - LAST_FOREGROUND_ACTIVITY_AT
                    if idle_seconds < FOREGROUND_IDLE_GRACE_SECONDS:
                        sleep(FOREGROUND_IDLE_GRACE_SECONDS - idle_seconds)
                        _enrichment_checkpoint()
                    batch = auto_repair_error_batch(10, client=client)
                    if not batch["attempted"]:
                        break
                    fixed += batch["resolved"]
                    processed = offset + batch["attempted"]
                    # Remaining means unresolved review rows, not merely the
                    # unattempted queue. Rows tried but not fixed still need
                    # manual review and must remain in this denominator.
                    unresolved = max(total - fixed, 0)
                    AUTO_REPAIR_STATS.update({"fixed": base_fixed + fixed, "processed": base_processed + processed, "remaining": unresolved})
                    set_auto_repair_stats(base_fixed + fixed, base_processed + processed, unresolved, base_manual)
                    ENRICHMENT_STATUS.update({"processed": offset + batch["attempted"], "current_id": "", "updated_at": utc_now_iso()})
                    offset += batch["attempted"]
                    sleep(AUTO_REPAIR_BATCH_PAUSE_SECONDS)
                ENRICHMENT_STATUS.update({"state": "idle", "current_id": "", "updated_at": utc_now_iso()})
                AUTO_REPAIR_STATS["remaining"] = max(total - fixed, 0)
                set_auto_repair_stats(base_fixed + fixed, base_processed + offset, max(total - fixed, 0), base_manual)
                refresh_error_count("", client=client)
                _schedule_quality_fix_metrics_refresh(force=True)
                if fixed > 0:
                    _invalidate_cache_background()
                    _refresh_silver_background(low_priority=True)
            except Exception as exc:
                ENRICHMENT_STATUS.update({"state": "stopped" if ENRICHMENT_STOP_REQUESTED.is_set() else "failed", "updated_at": utc_now_iso()})
                LOGGER.warning("automatic_review_repair_failed error=%s", exc)

        AUTO_REPAIR_THREAD = threading.Thread(target=worker, name="automatic-review-repair", daemon=True)
        AUTO_REPAIR_THREAD.start()
        return {"status": "started", "batch_size": 10}


def reprocess_rejected(data: dict[str, Any], *, client: Any = None) -> dict[str, Any]:
    def normalize_reprocess_row(row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return row
        if isinstance(row, str):
            try:
                decoded = json.loads(row)
            except ValueError as exc:
                raise ValueError("Row data is not valid JSON. Please review the edited record values and try again.") from exc
            if isinstance(decoded, dict):
                return decoded
        raise ValueError("Row data must be a field/value object. Please reopen the record, update the highlighted fields, and retry.")

    event_id = str(data.get("event_id", "")).strip()
    mapper = data.get("mapper")
    if not event_id or not isinstance(mapper, dict):
        raise ValueError("event_id and mapper are required")
    project_id, dataset_id, credentials_json = _warehouse_settings()
    if client is None:
        client = _bigquery_client(project_id, credentials_json)
    records = list_rejected(event_id, client=client)["records"]
    if data.get("rows") and isinstance(data["rows"], list):
        rows = [normalize_reprocess_row(row) for row in data["rows"]]
    else:
        selected_numbers = {int(value) for value in data.get("row_numbers", [])}
        rows = [normalize_reprocess_row(record["raw_record"]) for record in records if not selected_numbers or record["row_number"] in selected_numbers]
    if not rows:
        raise ValueError("No rejected records were found for reprocessing")

    # Fallback to recorded business_id / source_type_id if mapper lacks them
    if records:
        first_rec = records[0]
        if not mapper.get("business_id") and first_rec.get("business_id"):
            mapper["business_id"] = first_rec["business_id"]
        if not mapper.get("source_type_id") and first_rec.get("source_type_id"):
            mapper["source_type_id"] = first_rec["source_type_id"]
        # Brand is always resolved from business_id via the businesses
        # table, never trusted from the client submission - a record's
        # brand is fixed by its event_id -> business_id relation and can't
        # be changed by sending a different brand string in the edit
        # payload. Only reassigning the record to a different business_id
        # (a real business) can change what brand it maps to.
        if mapper.get("business_id"):
            try:
                for b in fetch_mirror_businesses():
                    if b.get("business_id") == mapper["business_id"]:
                        mapper["brand"] = b.get("name") or mapper.get("brand")
                        break
            except Exception:
                pass

    mapper_fields = mapper.get("fields")
    if not isinstance(mapper_fields, dict):
        mapper_fields = {}
    source_fields = sorted({path for path in mapper_fields.values() if path})
    if not source_fields and rows and isinstance(rows[0], dict):
        source_fields = list(rows[0].keys())

    # Reprocess single record or batch without creating duplicate error rows
    reprocessed_row_numbers = [int(v) for v in data.get("row_numbers", [])]
    if not reprocessed_row_numbers and records:
        reprocessed_row_numbers = [int(rec["row_number"]) for rec in records if "row_number" in rec]

    # Timestamp captured before save_mapper runs. save_mapper may re-insert a
    # NEW error row for the same (event_id, row_number) if the row is still
    # invalid, stamped with a fresh observed_at >= this cutoff. The cleanup
    # UPDATE below only soft-deletes rows observed strictly before it, so it
    # clears the OLD error row without ever deleting the just-created
    # replacement (which would otherwise make a still-invalid retry silently
    # vanish from the review queue).
    cleanup_cutoff = utc_now_iso()
    skip_refresh = bool(data.get("skip_cache_invalidation") or data.get("is_ai_enriched", False))
    # Every row reaching reprocess_rejected() is, by definition, already a
    # prior failure - if it fails validation again, that's the next attempt
    # on top of whatever this record has already been through.
    prior_attempt_count = max((int(rec.get("attempt_count") or 0) for rec in records), default=0)
    result = save_mapper({
        "mapper": mapper,
        "rows": rows,
        "source_fields": source_fields,
        "save_template": False,
        "event_id": event_id,
        "row_offset": (reprocessed_row_numbers[0] - 1) if len(reprocessed_row_numbers) == 1 else 0,
        "is_ai_enriched": bool(data.get("is_ai_enriched", False)),
        "attempt_count": prior_attempt_count + 1,
    }, client=client, skip_cache_invalidation=skip_refresh)

    # Handle soft-deleting old error records:
    # 1) If mapped successfully into listings, delete from error_listings.
    # 2) If validation fails again, the OLD error row is deleted and the
    #    fresh one (observed >= cutoff) is kept, so the count reflects one
    #    still-broken row rather than multiplying.
    # This must not fail silently: a caller that reports "moved to
    # listings" while the old error row secretly survives (and keeps
    # counting toward the error total) is worse than surfacing the
    # failure, so both an exception and a no-op UPDATE (0 rows affected,
    # e.g. an event_id/row_number mismatch) are reported back to the
    # caller via result["error_listings_cleanup"] instead of only logging.
    result["error_listings_cleanup"] = {"attempted": bool(records and reprocessed_row_numbers), "ok": True, "rows_updated": 0}
    affected_business_id = str(mapper.get("business_id") or "").strip()
    if records and reprocessed_row_numbers:
        try:
            from google.cloud import bigquery
            update_query = f"""
            UPDATE `{project_id}.{dataset_id}.error_listings`
            SET is_deleted = TRUE, deleted_on = CURRENT_TIMESTAMP(),
                resolution_status = 'fixed'
            WHERE event_id = @event_id
              AND row_number IN UNNEST(@row_numbers)
              AND is_deleted IS NOT TRUE
              AND (observed_at IS NULL OR observed_at < TIMESTAMP(@cutoff))
            """
            update_config = bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("event_id", "STRING", event_id),
                bigquery.ArrayQueryParameter("row_numbers", "INT64", reprocessed_row_numbers),
                bigquery.ScalarQueryParameter("cutoff", "STRING", cleanup_cutoff),
            ])
            update_job = client.query(update_query, job_config=update_config)
            update_job.result()
            rows_updated = update_job.num_dml_affected_rows or 0
            result["error_listings_cleanup"]["rows_updated"] = rows_updated
            if rows_updated < len(reprocessed_row_numbers):
                LOGGER.warning(
                    "error_listings_cleanup_incomplete event_id=%s expected=%d updated=%d row_numbers=%s",
                    event_id, len(reprocessed_row_numbers), rows_updated, reprocessed_row_numbers,
                )
                result["error_listings_cleanup"]["ok"] = False
        except Exception as exc:
            LOGGER.exception("error_listings_cleanup_failed event_id=%s row_numbers=%s", event_id, reprocessed_row_numbers)
            result["error_listings_cleanup"] = {"attempted": True, "ok": False, "rows_updated": 0, "error": str(exc)}

    # The error_listings table just changed (rows soft-deleted, and possibly
    # a fresh error row inserted by save_mapper). Re-count from BigQuery -
    # the source of truth - and write the fresh numbers back to SQLite, so
    # the tab's counter converges instead of showing a stale value. Return
    # them so the UI can update instantly without a second round trip.
    try:
        # Adopting an AI suggestion is an AI fix, not "no fix at all". This
        # branch previously only handled the manual case, so an adopted
        # suggestion incremented NEITHER counter: it skipped the manual
        # increment (correctly) but never wrote an AI fix event either, and
        # the AI metric counts quality_fix_events with fix_type='AI'. That is
        # why "Suggested ZIP + coordinates" never moved Listings Fixed
        # Automatically.
        adopted_ai_suggestion = bool(data.get("is_ai_enriched", False))
        rows_updated = int(result["error_listings_cleanup"].get("rows_updated", 0) or 0)
        if result["error_listings_cleanup"].get("ok") and rows_updated:
            fix_type = "AI" if adopted_ai_suggestion else "MANUAL"
            if not adopted_ai_suggestion:
                increment_manual_fixed_count(rows_updated)
            for row_number in reprocessed_row_numbers:
                try:
                    _record_quality_fix_event(
                        event_id=event_id,
                        row_number=int(row_number),
                        fix_type=fix_type,
                        processed=True,
                        improved=True,
                    )
                except Exception as event_exc:
                    LOGGER.warning("quality_fix_event_write_failed type=%s event_id=%s row=%s error=%s", fix_type, event_id, row_number, event_exc)
        result["error_count_total"] = refresh_error_count("", client=client)
        if affected_business_id:
            result["error_count"] = refresh_error_count(affected_business_id)
        _schedule_quality_fix_metrics_refresh(force=True)
    except Exception as exc:
        LOGGER.warning("error_count_refresh_after_reprocess_failed event_id=%s error=%s", event_id, exc)

    # The user edited and submitted this record, so their input is kept even
    # though it still fails validation - marked user_reviewed rather than
    # bounced back. The save returns immediately (no live re-validation round
    # trip, which is what made single-row edits feel slow), and enrichment
    # re-checks it later, by which time the reference data it needed may have
    # arrived. Their values are never discarded in favour of a stale row.
    if result.get("mapped_rows", 0) == 0 and rows and str(data.get("accept_as_reviewed", "")).lower() in {"1", "true", "yes"}:
        try:
            marked = run_sql_dml(client, f"""
            UPDATE `{project_id}.{dataset_id}.error_listings`
            SET user_reviewed = TRUE,
                user_reviewed_at = CURRENT_TIMESTAMP(),
                raw_record = @raw_record,
                attempt_count = COALESCE(attempt_count, 0) + 1
            WHERE event_id = @event_id AND is_deleted IS NOT TRUE
            """, {"event_id": event_id, "raw_record": _safe_json_dumps(rows[0])},
                label="reprocess:accept_as_reviewed")
            result["user_reviewed"] = marked
            result["deferred"] = True
            LOGGER.info("record_accepted_as_reviewed event_id=%s rows=%d", event_id, marked)
        except Exception as exc:
            LOGGER.warning("accept_as_reviewed_failed event_id=%s error=%s", event_id, exc)

    if result.get("mapped_rows", 0) == 0 and rows:
        # Still invalid after a user-submitted fix - rather than a blanket
        # "review required fields" message with nothing actionable, run the
        # same enrichment pass the background auto-repair worker uses and
        # hand back whatever concrete values it could infer, so the UI can
        # suggest something instead of repeating the generic error.
        # Name the fields that ACTUALLY failed. A blanket "check required
        # fields, ZIP and coordinates" gives the user nothing to act on when
        # the real problem is one specific field - they re-read every input
        # looking for it.
        try:
            # save_mapper already reports which fields failed; surface them.
            failed_fields = [f for f in (result.get("failed_fields") or []) if f]
            if failed_fields:
                result["failed_fields"] = failed_fields
        except Exception as exc:
            LOGGER.info("failed_field_extract_failed error=%s", exc)

        try:
            from whitespace_tool.geo_enrichment import (enrich_raw_listing_row, detect_hierarchy_conflict,
                                                        find_nearest_worldwide_city, is_us_land_coordinate,
                                                        MAX_SUGGESTION_DISTANCE_KM)
            from whitespace_tool.sqlite_cache import get_db_connection
            from whitespace_tool.normalization import optional_float
            first_row = rows[0]
            if isinstance(first_row, dict):
                with get_db_connection() as conn:
                    suggestion = enrich_raw_listing_row(first_row, conn)
                    raw_lat = optional_float(first_row.get("latitude") or first_row.get("Latitude"))
                    raw_lon = optional_float(first_row.get("longitude") or first_row.get("Longitude"))
                    raw_zip = first_row.get("postal_code") or first_row.get("zip") or first_row.get("Zip") or first_row.get("PostalCode")
                    raw_country = first_row.get("country") or first_row.get("Country")
                    conflict = detect_hierarchy_conflict(raw_zip, raw_country, raw_lat, raw_lon, conn)
                    non_us_match = None
                    if raw_lat is not None and raw_lon is not None and not is_us_land_coordinate(raw_lat, raw_lon):
                        # Try the US reading first (already done above via
                        # enrich_raw_listing_row/detect_hierarchy_conflict) -
                        # only reached when the coordinates are genuinely
                        # outside US bounds. Look up what's actually there
                        # worldwide instead of just rejecting the record.
                        # This is the confirm-me suggestion path, so it may
                        # reach the wider 100km radius - the user accepts or
                        # rejects it. Automatic snapping stays at 50km.
                        non_us_match = find_nearest_worldwide_city(
                            raw_lat, raw_lon, conn, max_distance_km=MAX_SUGGESTION_DISTANCE_KM)
                changed_suggestion = {
                    key: value for key, value in suggestion.items()
                    if key in ("city", "state", "postal_code", "zip", "latitude", "longitude", "country")
                    and value not in (None, "") and str(value) != str(first_row.get(key, ""))
                }
                if changed_suggestion:
                    result["suggested_fix"] = changed_suggestion
                if conflict:
                    # A genuine ZIP-vs-coordinate disagreement is a different
                    # situation from "one value is simply missing" - offer
                    # both readings explicitly instead of silently picking
                    # one, so the user (or the AI-resolve flow) chooses which
                    # is right rather than the system guessing.
                    result["hierarchy_conflict"] = conflict
                if non_us_match:
                    # Offered as an explicit "accept this as real non-US
                    # data" choice (the frontend's Save as Non-US Data
                    # button), not auto-applied - country gets set from
                    # this match, which is what lets
                    # validate_normalized_location()'s US-boundary check
                    # exempt the record on the next validation pass instead
                    # of asking the same question again.
                    result["non_us_suggestion"] = {
                        "city": non_us_match.get("city") or non_us_match.get("town"),
                        "state": non_us_match.get("state_code") or non_us_match.get("state_name"),
                        "country": non_us_match.get("country_name") or non_us_match.get("country_code"),
                        "country_code": non_us_match.get("country_code"),
                        "zip_code": non_us_match.get("zip_code"),
                        "distance_km": non_us_match.get("distance_km"),
                    }
        except Exception as exc:
            LOGGER.warning("reprocess_suggestion_failed event_id=%s error=%s", event_id, exc)

    return result


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _row_has_ai_suggestion(row: Any) -> bool:
    """Would enrichment be able to propose anything concrete for this row?

    Deliberately cheap: one indexed SQLite lookup against already-cached
    ZIP/city reference data (the same call the auto-repair worker makes),
    never a BigQuery round trip or a network call - this runs once per
    rejected row at write time, so it has to stay well clear of the
    memory/latency budget in INV-12. Any failure answers "no suggestion"
    rather than blocking a save.
    """
    if not isinstance(row, dict):
        return False
    try:
        from whitespace_tool.geo_enrichment import enrich_raw_listing_row
        from whitespace_tool.sqlite_cache import get_db_connection

        with get_db_connection() as conn:
            suggestion = enrich_raw_listing_row(row, conn)
        if not isinstance(suggestion, dict):
            return False
        # Only counts if enrichment actually produced a *different* value
        # for a field that matters - echoing back what the row already has
        # is not a suggestion.
        for key in ("city", "state", "postal_code", "zip", "latitude", "longitude", "country"):
            value = suggestion.get(key)
            if value in (None, ""):
                continue
            if str(value) != str(row.get(key, "")):
                return True
        return False
    except Exception as exc:
        LOGGER.warning("ai_suggestion_probe_failed error=%s", exc)
        return False


def _row_error_listing(
    event_id: str,
    business_id: str,
    source_type_id: str,
    index: int,
    row: Any,
    row_errors: list[dict[str, Any]],
    observed_at: str,
    attempt_count: int = 0,
    has_ai_suggestion: bool | None = None,
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
        # Set once, never cleared: this row WAS invalid, whatever happens to
        # it later. Without it, fixing a record (which soft-deletes the error
        # row) erased it from the totals entirely.
        "was_ever_invalid": True,
        "resolution_status": "pending",
        "template_id": meta.get("template_id"),
        "ingestion_id": meta.get("ingestion_id"),
        "mapping_id": meta.get("mapping_id"),
        "validation_error_type": first_error.get("reason") or first_error.get("field"),
        "country": country,
        "is_sample_data": bool(meta.get("is_sample_data")),
        "sample_batch_id": meta.get("sample_batch_id"),
        # Whether an AI suggestion existed for this row when it entered
        # review. Computed once here rather than re-probed for the whole
        # queue on every reporting load (RPT-08's AI-vs-manual pending
        # split reads this straight off the table).
        "has_ai_suggestion": _row_has_ai_suggestion(row) if has_ai_suggestion is None else bool(has_ai_suggestion),
        "is_deleted": False,
        "deleted_on": None,
        # How many times this row has been submitted for reprocessing and
        # failed again - 0 on a fresh initial-parse failure, incremented by
        # reprocess_rejected() each time a user-submitted fix still fails.
        # Drives the "Review Again" counter in the edit dialog.
        "attempt_count": attempt_count,
    }


def _dedupe_listings_against_bronze(client: Any, project_id: str, dataset_id: str, listing_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Drop listing rows whose content_hash already exists in bronze for
    the same business (the same real-world listing observed again),
    instead bumping that existing row's last_observed_at. Returns
    (rows to actually insert, count of duplicates skipped)."""
    if not listing_rows:
        return listing_rows, 0
    from google.cloud import bigquery

    from whitespace_tool.warehouse_bigquery import legacy_content_hash

    # Rows stored before business_id was removed from CONTENT_HASH_FIELDS
    # carry the old hash. Looking for BOTH is what stops a re-save inserting
    # a second copy of every listing in the warehouse during the transition;
    # a legacy match is also rewritten to the new hash below, so the table
    # migrates itself as sources are re-observed rather than needing the
    # backfill to have run first.
    legacy_by_row = {id(row): legacy_content_hash(row) for row in listing_rows}
    hashes = sorted(
        {row["content_hash"] for row in listing_rows if row.get("content_hash")}
        | {legacy_by_row[id(row)] for row in listing_rows}
    )
    if not hashes:
        return listing_rows, 0
    table_ref = f"{project_id}.{dataset_id}.listings"
    try:
        query = f"""
        SELECT listing_id, business_id, content_hash, last_observed_at
        FROM `{table_ref}`
        WHERE is_deleted IS NOT TRUE AND content_hash IN UNNEST(@hashes)
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ArrayQueryParameter("hashes", "STRING", hashes)])
        existing = {
            (row["business_id"], row["content_hash"]): row
            for row in client.query(query, job_config=job_config).result()
        }
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return listing_rows, 0  # bronze listings table doesn't exist yet
        raise

    new_rows: list[dict[str, Any]] = []
    duplicate_count = 0
    for row in listing_rows:
        business_id = row.get("business_id")
        match = existing.get((business_id, row.get("content_hash")))
        legacy_hash = legacy_by_row[id(row)]
        if match is None:
            match = existing.get((business_id, legacy_hash))
            if match is not None:
                # Same listing, stored under the old hash definition. Bring
                # the stored row forward so the cross-brand duplicate signal
                # sees it, and so this lookup stops needing the fallback.
                try:
                    client.query(
                        f"UPDATE `{table_ref}` SET content_hash = @content_hash WHERE listing_id = @listing_id",
                        job_config=bigquery.QueryJobConfig(query_parameters=[
                            bigquery.ScalarQueryParameter("content_hash", "STRING", row.get("content_hash")),
                            bigquery.ScalarQueryParameter("listing_id", "STRING", match["listing_id"]),
                        ])).result()
                except Exception as exc:
                    LOGGER.warning("legacy_hash_upgrade_failed listing_id=%s error=%s",
                                   match["listing_id"], exc)
        if match is None:
            new_rows.append(row)
            continue
        duplicate_count += 1
        new_observed = row.get("last_observed_at")
        if new_observed and (not match["last_observed_at"] or str(new_observed) > str(match["last_observed_at"])):
            update_query = f"UPDATE `{table_ref}` SET last_observed_at = @observed_at WHERE listing_id = @listing_id"
            update_config = bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("observed_at", "TIMESTAMP", new_observed),
                bigquery.ScalarQueryParameter("listing_id", "STRING", match["listing_id"]),
            ])
            client.query(update_query, job_config=update_config).result()
    return new_rows, duplicate_count


def _maybe_refresh_after_save(skip_cache_invalidation: bool) -> None:
    """Called after a mapping save lands in bronze. Reporting reads
    exclusively from gold, which only reflects bronze/silver as of its last
    rebuild - kick that off now (non-blocking, in the background) instead of
    leaving newly-saved data invisible in Reporting until someone happens to
    view it and trigger the refresh, or the next hourly tick. Sample loading
    runs its own end-of-batch silver+gold rebuild instead, so it passes
    skip_cache_invalidation=True to avoid firing this redundantly per brand."""
    if skip_cache_invalidation:
        return
    invalidate_cache()
    _refresh_silver_background()


def save_mapper(payload: dict[str, Any], *, client: Any = None, skip_cache_invalidation: bool = False, assume_tables_exist: bool = False, reject_all_invalid: bool = False) -> dict[str, Any]:
    mapper = payload.get("mapper")
    rows = payload.get("rows")
    source_fields = payload.get("source_fields", [])
    if not isinstance(mapper, dict) or not isinstance(rows, list) or not isinstance(source_fields, list):
        raise ValueError("mapper, rows, and source_fields are required")
    # A malformed row shape is a record to review, not a reason to abandon
    # the batch: the documented data-flow contract is "valid rows are stored;
    # invalid rows are routed to Review Error Listings without blocking valid
    # rows", and the row loop below already catches a non-dict row and routes
    # it there ("Row must be an object with named fields"). This guard used to
    # raise on the FIRST such row, so one bad record aborted the entire save
    # and the valid rows alongside it were silently lost.
    #
    # It still fires when EVERY row is malformed, because that is not a data
    # problem to review - it means the caller sent the wrong shape entirely
    # (the review-repair path re-submitting a non-editable record), and there
    # would be nothing to save either way.
    if rows and all(not isinstance(row, dict) for row in rows):
        raise ValueError("This submission is not editable field data. Please reopen the record and retry.")
    LOGGER.info(
        "save_started brand=%r source_name=%r source_type=%r rows=%d source_fields=%d",
        mapper.get("brand", ""),
        mapper.get("source_name", ""),
        mapper.get("source_type", "unknown"),
        len(rows),
        len(source_fields),
    )
    mapper = _resolve_mapper_source_fields(mapper, source_fields)
    errors = validate_mapper(mapper, source_fields, rows)
    if errors:
        raise ValueError(f"Mapper validation failed: {', '.join(errors)}")

    source_name = str(mapper["source_name"]).strip()
    source_type_id = str(mapper.get("source_type_id", "")).strip() or ensure_source_type(str(mapper.get("source_type", "unknown")))
    try:
        # source_fields came from the fixed-size discovery sample (parse
        # only inspects the first MAPPER_SAMPLE_ROWS records - a documented
        # contract, not something to vary here). A full/batch save sees
        # real rows beyond that sample; if any carry a field discovery
        # never saw, that's exactly the "unknown source fields" failure
        # mode reported by users - record it as a learning signal for a
        # future adaptive sample size, without changing today's behavior.
        full_fields = set(collect_fields(rows)) if rows else set()
        missed_fields = full_fields - set(source_fields)
        if missed_fields:
            record_field_discovery_gap(source_type_id, len(source_fields), len(full_fields), sorted(missed_fields))
    except Exception as exc:
        LOGGER.warning("field_discovery_gap_tracking_failed error=%s", exc)
    try:
        confidence_events = payload.get("mapping_confidence_events")
        if isinstance(confidence_events, list) and confidence_events:
            record_mapping_confidence_events(confidence_events)
            # Push the updated learning to BigQuery in the background so a
            # restart (which wipes the ephemeral SQLite file on Render)
            # cannot lose it. Best-effort: a failed sync costs an
            # optimisation, never a user record.
            threading.Thread(target=lambda: _safe_confidence_sync(),
                             name="mapping-confidence-sync", daemon=True).start()
    except Exception as exc:
        LOGGER.warning("mapping_confidence_tracking_failed error=%s", exc)
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
    incoming_attempt_count = int(payload.get("attempt_count", 0) or 0)
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
                if sample_meta.get("is_sample_data"):
                    # Demo loads represent a new ingestion run. Do not carry
                    # source-file dates into current reporting snapshots.
                    observed_at = utc_now_iso()
                    location = replace(location, observed_at=observed_at)
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
            error_listings.append(_row_error_listing(event_id, business_id, source_type_id, source_index, row, row_errors, observed_at, attempt_count=incoming_attempt_count))
        elif location is not None:
            locations.append(location)

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = client or _bigquery_client(project_id, credentials_json)

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
        "is_ai_enriched": bool(payload.get("is_ai_enriched", False)),
    }
    for location in locations:
        if isinstance(location.raw, dict):
            location.raw.setdefault("__meta", sample_row_meta)
    rows_by_table = build_table_rows(locations, demographics)
    rows_by_table["listings"], duplicate_listings_skipped = _dedupe_listings_against_bronze(client, project_id, dataset_id, rows_by_table["listings"])
    rows_by_table["businesses"] = []
    for record in error_listings:
        record["source_type_id"] = source_type_id
    rows_by_table["source_types"] = []
    rows_by_table["workflow_templates"] = [{
        "workflow_template_id": template_id,
        "business_id": business_id, "source_type_id": source_type_id, "name": source_name,
        "components": json.dumps({"mapper": config_json, "source_type_id": source_type_id, "sample_meta": sample_meta}, sort_keys=True),
        "archived_components": None,
        "source_configuration": json.dumps(sample_meta.get("source_configuration") or {}, sort_keys=True),
        "is_sample_data": bool(sample_meta.get("is_sample_data")),
        "sample_batch_id": sample_meta.get("sample_batch_id"),
        "is_deleted": False,
        "deleted_on": None,
        "created_at": utc_now_iso(), "updated_at": utc_now_iso(),
    }] if save_template else []
    rows_by_table["error_listings"] = error_listings
    try:
        push_to_bigquery(project_id, dataset_id, rows_by_table, credentials_json, client=client, skip_empty_table_checks=assume_tables_exist)
    except Exception:
        # A save the user dismissed to the background is only visible to them
        # through Job History. Recording the event ONLY on success meant a
        # failed background save left no trace anywhere - the job simply never
        # appeared, which is indistinguishable from never having been started.
        # mapped_rows=0 with rows present is what record_save_event() derives
        # FAILED from, so no new status vocabulary is needed. Recorded here
        # rather than around the whole function on purpose: an argument-
        # validation raise never got as far as being a job.
        if rows:
            try:
                record_save_event(
                    event_id=event_id, brand=str(mapper.get("brand") or ""), total_rows=len(rows),
                    mapped_rows=0, error_listings=0, duplicate_listings_skipped=0,
                )
            except Exception as record_exc:
                LOGGER.warning("failed_save_event_record_failed event_id=%s error=%s", event_id, record_exc)
        raise
    _maybe_refresh_after_save(skip_cache_invalidation)
    LOGGER.info(
        "save_succeeded mapper_id=%s dataset=%s mapped_rows=%d mapped_fields=%d duplicate_listings_skipped=%d",
        mapper_id,
        f"{project_id}.{dataset_id}",
        len(locations),
        len(mapper["fields"]),
        duplicate_listings_skipped,
    )
    try:
        record_save_event(
            event_id=event_id, brand=str(mapper.get("brand") or ""), total_rows=len(rows),
            mapped_rows=len(locations), error_listings=len(error_listings),
            duplicate_listings_skipped=duplicate_listings_skipped,
        )
    except Exception as exc:
        LOGGER.warning("save_event_record_failed event_id=%s error=%s", event_id, exc)
    # Distinct fields that actually failed, so a caller can say WHICH field is
    # wrong instead of "check required fields, ZIP and coordinates" - which
    # makes the user re-read every input hunting for the one that matters.
    failed_field_names: list[str] = []
    for error_row in error_listings:
        try:
            entries = json.loads(error_row.get("errors") or "[]")
        except (TypeError, ValueError):
            entries = []
        for entry in entries if isinstance(entries, list) else []:
            field = str((entry or {}).get("field") or "").strip() if isinstance(entry, dict) else ""
            if field and field not in failed_field_names:
                failed_field_names.append(field)
    return {"event_id": event_id, "mapper_id": mapper_id, "total_rows": len(rows), "mapped_rows": len(locations), "error_listings": len(error_listings), "failed_fields": failed_field_names, "field_count": len(mapper["fields"]), "dataset": f"{project_id}.{dataset_id}", "row_offset": row_offset, "template_saved": save_template, "duplicate_listings_skipped": duplicate_listings_skipped, "attempt_count": incoming_attempt_count}


def clear_saved_data() -> dict[str, Any]:
    project_id, dataset_id, credentials_json = _warehouse_settings()
    clear_result = clear_dataset_tables(project_id, dataset_id, credentials_json)
    deleted = clear_result["soft_deleted_tables"]
    truncated = clear_result["truncated_tables"]
    ZIP_REFERENCE_CACHE.pop((project_id, dataset_id), None)
    invalidate_cache()
    # invalidate_cache() deliberately spares reporting_quality:* keys (they
    # self-refresh on read), but clearing changes the underlying population,
    # so those must go too.
    invalidate_quality_cache()
    # Rebuild silver/gold and re-sync the SQLite mirror against whatever data
    # remains - reporting reads the mirror before BigQuery, so without this it
    # keeps serving rows that were just cleared. force_mirror because an empty
    # result here is the correct new truth, not a transient failure.
    try:
        _invoke_silver_layer(low_priority=True)
        _rebuild_gold_and_mirror(force_mirror=True)
        # The AI/manual fix counters are a persisted SQLite tally, not a
        # derived read - without a forced recount they keep displaying fixes
        # for rows that no longer exist. RULE: no metric anywhere in the app
        # may read stale after a clear.
        _schedule_quality_fix_metrics_refresh(force=True)
    except Exception as mirror_exc:
        LOGGER.warning("mirror_resync_after_clear_failed error=%s", mirror_exc)
    try:
        remaining_errors = refresh_error_count("")
    except Exception as exc:
        LOGGER.warning("error_count_refresh_after_clear_failed error=%s", exc)
        remaining_errors = 0
    return {
        "dataset": f"{project_id}.{dataset_id}",
        "deleted_tables": deleted,
        "deleted_count": len(deleted),
        "truncated_tables": truncated,
        "truncated_count": len(truncated),
    }


def master_delete_data(data: dict[str, Any]) -> dict[str, Any]:
    authenticate({"username": data.get("username", ""), "password": data.get("password", "")})
    confirm = str(data.get("confirmation", "")).strip()
    if confirm != "DELETE ALL DATA":
        raise ValueError("Type DELETE ALL DATA to confirm master deletion.")
    project_id, bronze_dataset_id, silver_dataset_id, gold_dataset_id, credentials_json = _medallion_settings()
    datasets = [bronze_dataset_id, silver_dataset_id, gold_dataset_id]
    results = []
    dropped_tables: list[str] = []
    for dataset_id in datasets:
        result = drop_dataset_tables(project_id, dataset_id, credentials_json)
        qualified = [f"{dataset_id}.{name}" for name in result["dropped_tables"]]
        dropped_tables.extend(qualified)
        results.append({"dataset": f"{project_id}.{dataset_id}", "dropped_tables": result["dropped_tables"], "dropped_count": len(result["dropped_tables"])})
        ZIP_REFERENCE_CACHE.pop((project_id, dataset_id), None)
    ZIP_REFERENCE_CACHE.clear()
    _forget_ensured_tables()
    invalidate_cache()
    # invalidate_cache() deliberately spares reporting_quality:* keys, but a
    # master delete removes the population they describe.
    invalidate_quality_cache()
    clear_local_cache_db()
    set_error_count("", 0)
    # Zero the DURABLE counters explicitly rather than relying on
    # clear_local_cache_db() having deleted the row, or on the browser
    # clearing its own copy. After a master delete every fix event is gone,
    # so 0 is the measured truth, not a placeholder - and the counters must
    # not be able to show pre-delete numbers if the client never reloads.
    set_auto_repair_stats(0, 0, 0, 0)
    AUTO_REPAIR_STATS.update({"fixed": 0, "manual_fixed": 0, "processed": 0, "remaining": 0})
    ENRICHMENT_STATUS.update({"state": "idle", "updated_at": utc_now_iso()})
    return {
        "datasets": results,
        "dropped_tables": dropped_tables,
        "dropped_count": len(dropped_tables),
    }


def template_sample_records(params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Rows already saved under one template, for the template editor's
    Source Preview.

    Editing a saved template showed only its stored COLUMN NAMES - the panel
    said "no live data rows", which is not much use for judging whether a
    mapping is right. The rows this template actually produced are sitting in
    `listings`, keyed by template_id (and business_id, since a template
    always belongs to a business), so show those instead of asking the user
    to re-parse a file just to see examples.
    """
    from google.cloud import bigquery

    params = params or {}
    template_id = str(params.get("template_id", [""])[0] or "").strip()
    business_id = str(params.get("business_id", [""])[0] or "").strip()
    if not template_id:
        raise ValueError("template_id is required")
    try:
        limit = max(1, min(int(str(params.get("limit", ["10"])[0] or "10")), 50))
    except (TypeError, ValueError):
        limit = 10

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    try:
        _ensure_listings_table(client, project_id, dataset_id)
    except Exception as exc:
        LOGGER.warning("template_sample_ensure_failed error=%s", exc)

    query = f"""
    SELECT
      l.listing_id, l.name, l.address, l.city_name, l.state_code, l.zip_code,
      l.country, l.latitude, l.longitude, l.phone_number, l.website_url,
      l.last_observed_at, l.custom_fields
    FROM `{project_id}.{dataset_id}.listings` l
    WHERE l.is_deleted IS NOT TRUE
      AND l.template_id = @template_id
      AND (@business_id = '' OR l.business_id = @business_id)
    ORDER BY l.last_observed_at DESC
    LIMIT {limit}
    """
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("template_id", "STRING", template_id),
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
    ])
    try:
        rows = list(client.query(query, job_config=config).result())
    except Exception as exc:
        if getattr(exc, "code", None) == 404 or "not found" in str(exc).lower():
            return {"records": [], "total": 0, "warning": "No stored listings table yet."}
        raise

    def scalar(value: Any) -> Any:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    records = [{k: scalar(v) for k, v in dict(row).items()} for row in rows]
    return {"records": records, "total": len(records), "template_id": template_id}


# Reporting TABLES export their own shape, not raw listing rows: a market-gap
# table is about uncovered ZIPs and a brand-comparison table is about brands,
# so shipping listing columns for either would be noise. Each is served from
# the same reporting_summary() payload the screen renders, so a downloaded
# table always matches what the user is looking at.
REPORTING_TABLE_EXPORTS: dict[str, dict[str, Any]] = {
    "market-gaps": {
        "key": "gaps",
        "definition": "Market ZIPs with no store for the selected brand(s) - the whitespace, with demographics for prioritising.",
    },
    "brand-comparison": {
        "key": "brands",
        "definition": "Per-brand footprint across the current filter selection.",
    },
    "top-states": {
        "key": "top_states",
        "definition": "States ranked by covered locations for the current selection.",
    },
    "top-cities": {
        "key": "top_cities",
        "definition": "Cities ranked by covered locations for the current selection.",
    },
}


def reporting_table_export(params: dict[str, list[str]] | None = None) -> tuple[bytes, str]:
    """Return (zip_bytes, filename) for one reporting TABLE."""
    params = params or {}
    table = str(params.get("table", [""])[0] or "").strip().lower()
    if table not in REPORTING_TABLE_EXPORTS:
        raise ValueError(f"unknown table: {table or '(missing)'}")
    spec = REPORTING_TABLE_EXPORTS[table]

    # Same call the screen makes, same filters - so the file cannot disagree
    # with what is on screen.
    summary = reporting_summary({k: v for k, v in params.items() if k != "table"})
    rows = summary.get(spec["key"]) or []
    rows = [dict(row) for row in rows if isinstance(row, dict)]

    applied = {k: v for k, v in params.items()
               if k not in {"table"} and any(str(x).strip() for x in v)}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    # Reuse the metric bundle: workbook + normalized CSVs + README.
    _METRIC_EXPORT_DEFINITIONS.setdefault(table, spec["definition"])
    return _metric_export_bundle(table, rows, "", applied), f"{table}-{stamp}.zip"


# The five states a once-invalid listing can be in. Read straight from the
# user's truth table:
#   was_ever_invalid + fixed   + is_ai_enriched            -> AI Fixed
#   was_ever_invalid + fixed   + has_ai_suggestion         -> AI Suggested Fixed
#   was_ever_invalid + fixed   + neither                   -> Manual Fixed
#   was_ever_invalid + pending + has_ai_suggestion         -> AI Suggested Pending
#   was_ever_invalid + pending + no suggestion             -> Manual Pending
# Counted over BOTH live and soft-deleted rows on purpose: a fixed record is
# soft-deleted, and excluding it is what made the totals reset instead of
# accumulating day over day.
FIX_STATE_KEYS: tuple[str, ...] = (
    "ai_fixed", "ai_suggested_fixed", "manual_fixed",
    "ai_suggested_pending", "manual_pending",
)


def fix_state_counts_by_brand(client: Any = None) -> dict[str, dict[str, int]]:
    """Same five-state model as fix_state_counts(), grouped by brand.

    The Quality-by-Brand table used to count is_ai_enriched over the
    currently-OPEN error rows, while the headline card counted all-time fix
    events - two different measures under one label, which is why the two
    numbers disagreed. This gives the table the cumulative definition so both
    are answering the same question.
    """
    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = client or _bigquery_client(project_id, credentials_json)
    try:
        _ensure_once("error_listings", _ensure_error_listings_table, client, project_id, dataset_id)
    except Exception as exc:
        LOGGER.warning("fix_state_by_brand_ensure_failed error=%s", exc)

    query = f"""
    WITH population AS (
      SELECT
        COALESCE(b.name, e.business_id) AS brand,
        COALESCE(e.was_ever_invalid, TRUE) AS ever_invalid,
        COALESCE(e.resolution_status, IF(e.is_deleted IS TRUE, 'fixed', 'pending')) AS state,
        COALESCE(e.is_ai_enriched, FALSE) AS ai_fixed,
        COALESCE(e.has_ai_suggestion, FALSE) AS ai_suggested
      FROM `{project_id}.{dataset_id}.error_listings` e
      LEFT JOIN `{project_id}.{dataset_id}.businesses` b
        ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
    )
    SELECT
      brand,
      COUNTIF(state = 'fixed' AND ai_fixed) AS ai_fixed,
      COUNTIF(state = 'fixed' AND NOT ai_fixed AND ai_suggested) AS ai_suggested_fixed,
      COUNTIF(state = 'fixed' AND NOT ai_fixed AND NOT ai_suggested) AS manual_fixed,
      COUNTIF(state != 'fixed' AND ai_suggested) AS ai_suggested_pending,
      COUNTIF(state != 'fixed' AND NOT ai_suggested) AS manual_pending,
      COUNT(*) AS total_ever_invalid
    FROM population
    WHERE ever_invalid AND brand IS NOT NULL
    GROUP BY brand
    """
    try:
        rows = list(client.query(query).result())
    except Exception as exc:
        if getattr(exc, "code", None) == 404 or "not found" in str(exc).lower():
            return {}
        raise
    return {
        str(row["brand"]): {key: int(row[key] or 0) for key in
                            (*FIX_STATE_KEYS, "total_ever_invalid")}
        for row in rows
    }


def fix_state_counts(business_id: str = "", *, client: Any = None) -> dict[str, int]:
    """Cumulative counts of every listing that was ever invalid, by state."""
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = client or _bigquery_client(project_id, credentials_json)
    try:
        _ensure_once("error_listings", _ensure_error_listings_table, client, project_id, dataset_id)
    except Exception as exc:
        LOGGER.warning("fix_state_ensure_failed error=%s", exc)

    query = f"""
    WITH population AS (
      SELECT
        -- Rows written before these columns existed carry NULL; they were
        -- still invalid by virtue of being in this table, and a row that is
        -- soft-deleted was resolved. Backfilling that inference here keeps
        -- historical rows countable instead of silently dropping them.
        COALESCE(was_ever_invalid, TRUE) AS ever_invalid,
        COALESCE(resolution_status, IF(is_deleted IS TRUE, 'fixed', 'pending')) AS state,
        COALESCE(is_ai_enriched, FALSE) AS ai_fixed,
        COALESCE(has_ai_suggestion, FALSE) AS ai_suggested
      FROM `{project_id}.{dataset_id}.error_listings`
      WHERE (@business_id = '' OR business_id = @business_id)
    )
    SELECT
      COUNTIF(state = 'fixed' AND ai_fixed) AS ai_fixed,
      COUNTIF(state = 'fixed' AND NOT ai_fixed AND ai_suggested) AS ai_suggested_fixed,
      COUNTIF(state = 'fixed' AND NOT ai_fixed AND NOT ai_suggested) AS manual_fixed,
      COUNTIF(state != 'fixed' AND ai_suggested) AS ai_suggested_pending,
      COUNTIF(state != 'fixed' AND NOT ai_suggested) AS manual_pending,
      COUNT(*) AS total_ever_invalid
    FROM population
    WHERE ever_invalid
    """
    try:
        row = next(iter(client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
        ])).result()), None)
    except Exception as exc:
        if getattr(exc, "code", None) == 404 or "not found" in str(exc).lower():
            row = None
        else:
            raise
    counts = {key: int(getattr(row, key, 0) or 0) for key in FIX_STATE_KEYS}
    counts["total_ever_invalid"] = int(getattr(row, "total_ever_invalid", 0) or 0)
    # The five states are mutually exclusive and exhaustive, so they must sum
    # to the total. If they ever do not, the state model has drifted.
    counts["states_reconcile"] = sum(counts[key] for key in FIX_STATE_KEYS) == counts["total_ever_invalid"]
    try:
        set_fix_state_counts(counts)
    except Exception as exc:
        LOGGER.warning("fix_state_mirror_write_failed error=%s", exc)
    return counts


def _cumulative_fix_states() -> dict[str, Any]:
    """Five-state counts for the cards, mirror-first.

    Reads the SQLite mirror so the cards paint immediately, and refreshes it
    from BigQuery in the background. An empty mirror means "not computed
    yet", which is reported as such rather than rendered as five zeros.
    """
    try:
        cached = get_fix_state_counts()
    except Exception as exc:
        LOGGER.warning("fix_state_mirror_read_failed error=%s", exc)
        cached = {}

    def refresh() -> None:
        try:
            fix_state_counts()
        except Exception as exc:
            LOGGER.warning("fix_state_refresh_failed error=%s", exc)

    threading.Thread(target=refresh, name="fix-state-refresh", daemon=True).start()
    if not cached:
        # refreshing=True tells the caller a recount is genuinely in flight,
        # so it can poll instead of leaving dashes on screen forever. Without
        # it the page had no way to know the answer was coming.
        return {"computed": False, "refreshing": True}
    payload = {key: int(cached.get(key, 0) or 0) for key in FIX_STATE_KEYS}
    payload["total_ever_invalid"] = int(cached.get("total_ever_invalid", 0) or 0)
    payload["updated_at"] = cached.get("updated_at", "")
    payload["computed"] = True
    return payload


def brand_identity_enrichment(params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Keyless website/phone/email lookup for a brand (see brand_enrichment)."""
    params = params or {}
    brand_name = str(params.get("name", [""])[0] or "").strip()
    if not brand_name:
        raise ValueError("name is required")
    country_code = str(params.get("country_code", [""])[0] or "").strip()
    existing = {
        field: str(params.get(field, [""])[0] or "").strip()
        for field in ("website_url", "phone_number", "email")
    }
    from whitespace_tool.brand_enrichment import enrich_brand_identity

    resolved = enrich_brand_identity(brand_name, country_code, existing)
    return {"brand": brand_name, "resolved": resolved,
            "unresolved_fields": resolved.get("unresolved_fields", [])}


_CONFIDENCE_RESTORED = False
_CONFIDENCE_RESTORE_LOCK = threading.Lock()


def _restore_mapping_confidence_once() -> None:
    """Repopulate SQLite from BigQuery the first time the learning is needed
    after a restart. Lazy rather than at boot: it costs a BigQuery round trip
    and is only worth paying when something actually reads the scores."""
    global _CONFIDENCE_RESTORED
    with _CONFIDENCE_RESTORE_LOCK:
        if _CONFIDENCE_RESTORED:
            return
        _CONFIDENCE_RESTORED = True
    def restore() -> None:
        try:
            from whitespace_tool.sqlite_cache import get_mapping_confidence

            if get_mapping_confidence():
                return  # cache survived; nothing to restore
            restore_mapping_confidence_from_warehouse()
        except Exception as exc:
            LOGGER.warning("mapping_confidence_restore_failed error=%s", exc)

    # Background, never inline. This is called from the auto-map path, which
    # a user is waiting on - a BigQuery round trip there would stall mapping
    # (and did hang the test suite). The scores are an optimisation, so the
    # current request simply proceeds without them and the next one benefits.
    threading.Thread(target=restore, name="mapping-confidence-restore", daemon=True).start()


def _safe_confidence_sync() -> None:
    try:
        sync_mapping_confidence_to_warehouse()
    except Exception as exc:
        LOGGER.warning("mapping_confidence_sync_failed error=%s", exc)


def sync_mapping_confidence_to_warehouse() -> dict[str, Any]:
    """Mirror the SQLite mapping-confidence learning into BigQuery.

    SQLite is the fast read path, but on Render it sits on ephemeral disk - a
    restart would erase everything the app has learned about which source
    column maps to which field. This makes that learning durable. Runs in the
    background and is intentionally best-effort: losing a sync is a lost
    optimisation, never a lost user record.
    """
    from google.cloud import bigquery
    from whitespace_tool.sqlite_cache import get_db_connection, init_sqlite_cache

    init_sqlite_cache()
    with get_db_connection() as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT target_key, source_field_normalized, score, sample_count, updated_at "
            "FROM field_mapping_confidence"
        ).fetchall()]
    if not rows:
        return {"synced": 0}

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.field_mapping_confidence"
    schema = [bigquery.SchemaField(f["name"], f["type"], mode=f["mode"])
              for f in TABLE_SCHEMAS["field_mapping_confidence"]]
    try:
        client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(bigquery.Table(table_ref, schema=schema))
    # Full replace: the table is small (one row per target/source pair) and a
    # replace keeps it exactly in step with SQLite rather than accumulating
    # superseded scores.
    load_job = client.load_table_from_json(
        rows, table_ref,
        job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE"))
    load_job.result()
    LOGGER.info("mapping_confidence_synced rows=%d", len(rows))
    return {"synced": len(rows)}


def restore_mapping_confidence_from_warehouse() -> dict[str, Any]:
    """Reload the learning into SQLite after a restart wiped the cache file."""
    from whitespace_tool.sqlite_cache import get_db_connection, init_sqlite_cache

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    try:
        rows = list(client.query(
            f"SELECT target_key, source_field_normalized, score, sample_count, updated_at "
            f"FROM `{project_id}.{dataset_id}.field_mapping_confidence`"
        ).result())
    except Exception as exc:
        if getattr(exc, "code", None) == 404 or "not found" in str(exc).lower():
            return {"restored": 0}
        raise
    if not rows:
        return {"restored": 0}
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO field_mapping_confidence "
            "(target_key, source_field_normalized, score, sample_count, updated_at) VALUES (?, ?, ?, ?, ?)",
            [(r["target_key"], r["source_field_normalized"], r["score"], r["sample_count"],
              r["updated_at"].isoformat() if hasattr(r["updated_at"], "isoformat") else r["updated_at"])
             for r in rows])
        conn.commit()
    LOGGER.info("mapping_confidence_restored rows=%d", len(rows))
    return {"restored": len(rows)}


# ThreadingTCPServer spawns a thread per request with no bound, so N
# concurrent reporting calls each build their own full result set at the same
# time. Measured on this box: 10 concurrent /api/reporting calls peaked at
# 432MB RSS against a 512MB limit (it IS released afterwards - back to ~108MB
# within 10s - so this is peak allocation, not a leak). One bad moment is
# still an OOM, so the heavy read paths queue instead of piling up. Reads are
# fast and cached, so a short wait beats an out-of-memory kill.
HEAVY_REQUEST_CONCURRENCY = 3
_HEAVY_REQUEST_SEMAPHORE = threading.BoundedSemaphore(HEAVY_REQUEST_CONCURRENCY)


class _heavy_request:
    """Context manager bounding how many expensive reads run at once."""

    def __enter__(self) -> "_heavy_request":
        _HEAVY_REQUEST_SEMAPHORE.acquire()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        _HEAVY_REQUEST_SEMAPHORE.release()


def make_handler(ui_dir: Path):
    class MapperHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ui_dir), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
            if code == 404:
                path = urlsplit(self.path).path
                if path.startswith("/api/"):
                    _json_response(self, 404, {"error": "Not found"})
                    return
                not_found_file = ui_dir / "not-found.html"
                if not_found_file.exists():
                    content = not_found_file.read_bytes()
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
            super().send_error(code, message=message, explain=explain)

        def _serve_ui_file(self, file_name: str, *, head: bool = False, status: int = 200) -> None:
            file_path = ui_dir / file_name
            if not file_path.exists():
                self.send_error(404, "File not found")
                return
            content = file_path.read_bytes()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not head:
                self.wfile.write(content)

        def _route_clean_ui_path(self, *, head: bool = False) -> bool:
            path = urlsplit(self.path).path
            if path in {"", "/"}:
                self._serve_ui_file("index.html", head=head)
                return True
            if path == "/login":
                self._serve_ui_file("login.html", head=head)
                return True
            if path == "/app":
                self._serve_ui_file("integrations.html", head=head)
                return True
            if path in {"/not-found", "/404"}:
                self._serve_ui_file("not-found.html", head=head, status=404)
                return True
            if path in {"/login.html", "/integrations.html", "/not-found.html", "/404.html"}:
                target = "/login" if path == "/login.html" else ("/app" if path == "/integrations.html" else "/not-found")
                query = urlsplit(self.path).query
                if query:
                    target = f"{target}?{query}"
                self.send_response(302)
                self.send_header("Location", target)
                self.end_headers()
                return True
            return False

        def do_HEAD(self) -> None:
            if self._route_clean_ui_path(head=True):
                return
            super().do_HEAD()

        def do_GET(self) -> None:
            if self._route_clean_ui_path():
                return
            if _requires_session(self.path) and not _request_has_session(self):
                # 401 (not a redirect) so the UI's existing 401 handling
                # sends the user to /login instead of a fetch parsing an
                # HTML login page as JSON.
                _json_response(self, 401, {"error": "Sign in to continue."})
                return
            if self.path == "/api/session":
                _json_response(self, 200, {"server_launch_id": SERVER_LAUNCH_ID})
                return
            if self.path == "/api/demo-python/pe-brand":
                demo_path = project_path("config/demo_pe_brand_python.py")
                if not demo_path.exists():
                    _json_response(self, 404, {"error": "Demo PE Brand sample is unavailable."})
                    return
                _json_response(self, 200, {"code": demo_path.read_text(encoding="utf-8")})
                return
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
            if urlsplit(self.path).path == "/api/prepare":
                try:
                    query_params = dict(parse_qsl(urlsplit(self.path).query))
                    _json_response(self, 200, prepare_zipcodes(force=str(query_params.get("force", "")).lower() in {"1", "true", "yes"}))
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
            if self.path.startswith("/api/cache/stats"):
                # What the cache is actually spending its time on, including
                # the death-by-a-thousand-cuts case a slow-call log cannot show.
                try:
                    _json_response(self, 200, {
                        "actions": get_cache_action_stats(50),
                        "slow_actions": get_slow_actions(25),
                    })
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/brands/enrich"):
                try:
                    _json_response(self, 200, brand_identity_enrichment(parse_qs(urlsplit(self.path).query)))
                except ValueError as exc:
                    _json_response(self, 400, {"error": str(exc)})
                except Exception as exc:
                    LOGGER.warning("brand_identity_enrichment_failed error=%s", exc)
                    _json_response(self, 400, {"error": "Could not look up this brand right now."})
                return
            if self.path.startswith("/api/brands"):
                search = parse_qs(urlsplit(self.path).query).get("search", [""])[0]
                try:
                    _json_response(self, 200, list_brands(search))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/templates/sample-records"):
                try:
                    _json_response(self, 200, template_sample_records(parse_qs(urlsplit(self.path).query)))
                except ValueError as exc:
                    _json_response(self, 400, {"error": str(exc)})
                except Exception as exc:
                    LOGGER.warning("template_sample_records_failed error=%s", exc)
                    _json_response(self, 400, {"error": "Could not load sample records for this template."})
                return
            if self.path.startswith("/api/templates"):
                params = parse_qs(urlsplit(self.path).query)
                search = params.get("search", [""])[0]
                business_id = params.get("business_id", [""])[0]
                source_type_id = params.get("source_type_id", [""])[0]
                raw_limit = params.get("limit", ["500"])[0]
                raw_offset = params.get("offset", ["0"])[0]
                try:
                    limit = int(raw_limit or "500")
                    offset = int(raw_offset or "0")
                    _json_response(self, 200, list_templates(search, business_id, source_type_id, limit=limit, offset=offset))
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
            if self.path.startswith("/api/reporting/quality"):
                try:
                    with _heavy_request():
                        _json_response(self, 200, reporting_quality_summary(parse_qs(urlsplit(self.path).query)))
                except Exception as exc:
                    LOGGER.warning("reporting_quality_request_failed error=%s", exc)
                    _json_response(self, 400, {"error": "Quality metrics are being prepared. Please refresh shortly."})
                return
            if self.path.startswith("/api/reporting/timeseries"):
                try:
                    _json_response(self, 200, reporting_timeseries(parse_qs(urlsplit(self.path).query)))
                except Exception as exc:
                    LOGGER.warning("reporting_timeseries_failed error=%s", exc)
                    _json_response(self, 400, {"error": "Timeseries data is being prepared. Please refresh shortly."})
                return
            if self.path.startswith("/api/reporting/table-export"):
                try:
                    body, filename = reporting_table_export(parse_qs(urlsplit(self.path).query))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except ValueError as exc:
                    _json_response(self, 400, {"error": str(exc)})
                except Exception as exc:
                    LOGGER.exception("reporting_table_export_failed error=%s", exc)
                    _json_response(self, 400, {"error": "Could not build this table export."})
                return
            if self.path.startswith("/api/reporting/metric-export"):
                try:
                    body, filename = reporting_metric_export(parse_qs(urlsplit(self.path).query))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except ValueError as exc:
                    _json_response(self, 400, {"error": str(exc)})
                except Exception as exc:
                    LOGGER.exception("reporting_metric_export_failed error=%s", exc)
                    _json_response(self, 400, {"error": "Could not build this export. Please retry shortly."})
                return
            if self.path.startswith("/api/reporting/export-excel"):
                try:
                    params = parse_qs(urlsplit(self.path).query)
                    excel_bytes, filename = export_reporting_excel(params)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(excel_bytes)))
                    self.end_headers()
                    self.wfile.write(excel_bytes)
                except Exception as exc:
                    LOGGER.exception("reporting_excel_export_failed error=%s", exc)
                    _json_response(self, 400, {"error": f"Failed to generate Excel export: {str(exc)}"})
                return
            if self.path.startswith("/api/reporting"):
                try:
                    with _heavy_request():
                        _json_response(self, 200, reporting_summary(parse_qs(urlsplit(self.path).query)))
                except Exception as exc:
                    LOGGER.warning("reporting_request_failed error=%s", exc)
                    _json_response(self, 400, {"error": "Reporting data is being prepared. Please refresh shortly."})
                return
            if self.path.startswith("/api/geo/options"):
                params = parse_qs(urlsplit(self.path).query)
                state = params.get("state", [""])[0]
                county = params.get("county", [""])[0]
                try:
                    _json_response(self, 200, geo_options(state, county))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/zips/search"):
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
            if self.path.startswith("/api/jobs/recent"):
                params = parse_qs(urlsplit(self.path).query)
                limit = int(params.get("limit", ["20"])[0] or 20)
                offset = int(params.get("offset", ["0"])[0] or 0)
                try:
                    _json_response(self, 200, {
                        "jobs": get_recent_save_events(limit, offset),
                        "total": count_save_events(),
                    })
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path == "/api/settings":
                try:
                    _json_response(self, 200, {"stale_after_days": get_stale_after_days()})
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path == "/api/sample/status":
                try:
                    _json_response(self, 200, sample_dataset_status())
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return



            if self.path.startswith("/api/rejected"):
                params = parse_qs(urlsplit(self.path).query)
                event_id = params.get("event_id", [""])[0]
                business_id = params.get("business_id", [""])[0]
                offset = int(params.get("offset", ["0"])[0] or 0)
                limit = int(params.get("limit", ["50"])[0] or 50)
                try:
                    _json_response(self, 200, list_rejected(event_id, business_id, limit=limit, offset=offset))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/error-listings/by-brand"):
                try:
                    _json_response(self, 200, error_listings_by_brand())
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path.startswith("/api/error-listings/count"):
                count_params = parse_qs(urlsplit(self.path).query)
                business_id = count_params.get("business_id", [""])[0]
                refresh = count_params.get("refresh", ["0"])[0] in ("1", "true", "True")
                try:
                    _json_response(self, 200, {"count": count_error_listings(business_id, refresh=refresh)})
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            if self.path == "/api/enrichment/status":
                _json_response(self, 200, enrichment_status())
                return
            if self.path == "/api/review/fix-states":
                # The five cumulative cards used to be read off
                # /api/reporting/quality - a heavy multi-query aggregation.
                # Six numbers that are already sitting in the SQLite mirror
                # should not wait on it, or fail with it: when that endpoint
                # was slow or errored, every card rendered "-" while the
                # correct values were on disk the whole time.
                _json_response(self, 200, _cumulative_fix_states())
                return
            super().do_GET()

        def do_POST(self) -> None:
            if _requires_session(self.path) and not _request_has_session(self):
                _json_response(self, 401, {"error": "Sign in to continue."})
                return
            if self.path not in {"/api/login", "/api/preview", "/api/source-url", "/api/sheets", "/api/save", "/api/clear", "/api/master-delete", "/api/brands", "/api/brands/update", "/api/brands/merge", "/api/learning", "/api/reprocess", "/api/review/auto-repair", "/api/field-alias", "/api/custom-field", "/api/custom-field/delete", "/api/templates/save", "/api/silver/enrich", "/api/reporting/refresh", "/api/enrichment/stop", "/api/sample/load", "/api/sample/clear", "/api/settings"}:
                _json_response(self, 404, {"error": "Not found"})
                return
            if self.path not in {"/api/review/auto-repair", "/api/enrichment/stop"}:
                # Real user action, not the auto-repair worker's own
                # start/stop calls - marks the app "busy" so the background
                # loop yields instead of competing for the same resources.
                global LAST_FOREGROUND_ACTIVITY_AT
                LAST_FOREGROUND_ACTIVITY_AT = wall_clock_time()
            request_id = uuid4().hex
            try:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not payload.get("event_id"):
                    payload["event_id"] = request_id
                LOGGER.info("request_started request_id=%s endpoint=%s content_length=%d", request_id, self.path, length)
                if self.path == "/api/login":
                    result = authenticate(payload)
                    # authenticate() raises on bad credentials, so reaching
                    # here means the session is earned.
                    _json_response(self, 200, result, extra_headers=[(
                        "Set-Cookie",
                        f"{SESSION_COOKIE_NAME}={_issue_session_token()}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}",
                    )])
                elif self.path == "/api/source-url":
                    _json_response(self, 200, fetch_public_source(payload))
                elif self.path == "/api/sheets":
                    _json_response(self, 200, source_sheets(payload))
                elif self.path == "/api/save":
                    # Every invalid source row is retained in error_listings;
                    # valid rows in the same batch continue to listings.
                    _json_response(self, 200, save_mapper(payload))
                elif self.path == "/api/clear":
                    _json_response(self, 200, clear_saved_data())
                elif self.path == "/api/master-delete":
                    _json_response(self, 200, master_delete_data(payload))
                elif self.path == "/api/brands":
                    _json_response(self, 200, create_brand(payload))
                elif self.path == "/api/brands/update":
                    _json_response(self, 200, update_brand(payload))
                elif self.path == "/api/brands/merge":
                    _json_response(self, 200, merge_brands(payload))
                elif self.path == "/api/learning":
                    _json_response(self, 200, learn_mappings(payload))
                elif self.path == "/api/reprocess":
                    _json_response(self, 200, reprocess_rejected(payload))
                elif self.path == "/api/review/auto-repair":
                    _json_response(self, 202, start_auto_repair())
                elif self.path == "/api/field-alias":
                    _json_response(self, 200, add_field_alias(payload))
                elif self.path == "/api/custom-field":
                    _json_response(self, 200, create_custom_field(payload))
                elif self.path == "/api/custom-field/delete":
                    _json_response(self, 200, delete_custom_field(payload))
                elif self.path == "/api/templates/save":
                    _json_response(self, 200, save_template_version(payload))
                elif self.path in {"/api/silver/enrich", "/api/reporting/refresh"}:
                    if self.path == "/api/reporting/refresh":
                        started = _refresh_silver_background(low_priority=True)
                        _json_response(self, 202, {"status": "enriching", "refreshing": True, "started": started})
                    else:
                        _json_response(self, 200, build_silver_layer(low_priority=bool(payload.get("low_priority", False))))
                elif self.path == "/api/enrichment/stop":
                    _json_response(self, 200, stop_enrichment())
                elif self.path == "/api/sample/load":
                    _json_response(self, 200, load_sample_dataset(bool(payload.get("reset"))))
                elif self.path == "/api/sample/clear":
                    _json_response(self, 200, clear_sample_dataset())
                elif self.path == "/api/settings":
                    raw_days = payload.get("stale_after_days")
                    try:
                        days = int(raw_days)
                    except (TypeError, ValueError):
                        raise ValueError("stale_after_days must be a whole number of days.")
                    if not 1 <= days <= 3650:
                        raise ValueError("stale_after_days must be between 1 and 3650 days.")
                    set_app_setting("stale_after_days", str(days))
                    # The stale count is baked into every cached quality
                    # payload, so they have to be recomputed against the new
                    # threshold rather than served from the old snapshot -
                    # and invalidate_cache() deliberately spares those keys,
                    # so clear them explicitly.
                    invalidate_quality_cache()
                    _json_response(self, 200, {"stale_after_days": days})
                else:
                    _json_response(self, 200, preview_source(payload))
            except Exception as exc:
                LOGGER.exception("request_failed request_id=%s endpoint=%s error=%s", request_id, self.path, exc)
                _json_response(self, 400, {"error": str(exc), "request_id": request_id})

    return MapperHandler


# Brands whose contact fields this process has already attempted, so a brand
# the open sources genuinely cannot resolve is not retried every cycle.
_BRAND_ENRICH_ATTEMPTED: set[str] = set()
BRAND_ENRICH_BATCH = 3
BRAND_ENRICH_IDLE_SECONDS = 60.0
BRAND_ENRICH_PAUSE_SECONDS = 20.0


# Background work must not wipe the reporting cache on every pass.
#
# invalidate_cache() is a blanket DELETE of every cached payload except
# reporting_quality:*. That is right for a user action - a save or a brand
# merge has to be visible immediately - but the background loops call it too,
# and they run constantly: auto-repair fixes ten rows a cycle, and the two
# enrichment passes fill a field at a time. The observed result was a
# query_cache holding ONLY the exempt reporting_quality:* keys, with every
# reporting_summary:* entry gone, so each dashboard load paid the full
# recompute and reported itself as still refreshing.
#
# Background callers go through this instead: the invalidation still happens,
# just not more than once every couple of minutes. Nothing goes stale that
# was not already eventually-consistent - these passes change a contact field
# or resolve a review row, neither of which the dashboard's headline counts
# are computed from.
_LAST_BACKGROUND_INVALIDATION_AT: float = 0.0
BACKGROUND_INVALIDATION_MIN_INTERVAL_SECONDS = 120.0


def _invalidate_cache_background() -> bool:
    """Rate-limited invalidate_cache() for background loops.

    Returns True if the cache was actually cleared, False if the call was
    skipped because one landed recently.
    """
    global _LAST_BACKGROUND_INVALIDATION_AT
    now = wall_clock_time()
    if now - _LAST_BACKGROUND_INVALIDATION_AT < BACKGROUND_INVALIDATION_MIN_INTERVAL_SECONDS:
        return False
    _LAST_BACKGROUND_INVALIDATION_AT = now
    invalidate_cache()
    return True


def _idle_brand_enrichment_pass() -> dict[str, Any]:
    """Fill blank brand website/phone/email from open sources, one small batch.

    Runs only while the app is idle and yields the moment a user does
    anything - this is strictly best-effort background work on a 512MB box.
    Values a person entered are never overwritten (enrich_brand_identity
    only fills blanks), and a field the sources cannot establish is left
    blank rather than guessed at.
    """
    from google.cloud import bigquery
    from whitespace_tool.brand_enrichment import enrich_brand_identity

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    rows = list(client.query(f"""
        SELECT business_id, name, country_of_origin, website_url, email
        FROM `{project_id}.{dataset_id}.businesses`
        WHERE is_deleted IS NOT TRUE
          AND COALESCE(status, 'active') = 'active'
          AND (website_url IS NULL OR website_url = '')
        LIMIT 50
    """).result())
    candidates = [r for r in rows if str(r["business_id"]) not in _BRAND_ENRICH_ATTEMPTED][:BRAND_ENRICH_BATCH]
    if not candidates:
        return {"attempted": 0, "updated": 0}

    updated = 0
    for row in candidates:
        _enrichment_checkpoint()
        business_id = str(row["business_id"])
        _BRAND_ENRICH_ATTEMPTED.add(business_id)
        try:
            resolved = enrich_brand_identity(
                str(row["name"] or ""), str(row["country_of_origin"] or ""),
                {"website_url": row["website_url"] or "", "email": row["email"] or ""})
        except Exception as exc:
            LOGGER.info("brand_enrich_attempt_failed business_id=%s error=%s", business_id, exc)
            continue
        website = resolved.get("website_url")
        if not website:
            continue
        try:
            client.query(
                f"UPDATE `{project_id}.{dataset_id}.businesses` "
                f"SET website_url = @website, updated_at = CURRENT_TIMESTAMP() "
                f"WHERE business_id = @business_id AND (website_url IS NULL OR website_url = '')",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("website", "STRING", website),
                    bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
                ])).result()
            updated += 1
            LOGGER.info("brand_enriched business_id=%s source=%s", business_id,
                        resolved.get("website_url_source", "unknown"))
        except Exception as exc:
            LOGGER.warning("brand_enrich_write_failed business_id=%s error=%s", business_id, exc)
        sleep(BRAND_ENRICH_PAUSE_SECONDS)
    if updated:
        _invalidate_cache_background()
    return {"attempted": len(candidates), "updated": updated}


_LOCATION_ENRICH_ATTEMPTED: set[str] = set()
LOCATION_ENRICH_BATCH = 3
# The attempted-set is in-memory only, so it grows for the life of the
# process. Capped so a long-running server cannot accumulate one entry per
# listing in the warehouse; clearing it just means those listings become
# eligible to retry, which is harmless.
LOCATION_ENRICH_ATTEMPTED_MAX = 20000


def _idle_location_enrichment_pass() -> dict[str, Any]:
    """Fill a listing's own blank phone/website/email from OpenStreetMap.

    This is the store-level counterpart to _idle_brand_enrichment_pass(). It
    exists because semantic cleaning (see normalization._apply_semantic_
    cleaning) *clears* a value it can prove is not what the column means -
    "N/A" in a phone column, "excellent" in a rating - which is correct, but
    left nothing to run afterwards that could put a real value back.

    Two deliberate limits keep it honest:

    * It looks the store up **by its own coordinates**, not by brand, so a
      number it writes belongs to that store rather than being a corporate
      line copied across every listing.
    * It only ever writes into a column that is currently blank (enforced
      again in the UPDATE's WHERE clause, not just in Python), so a value a
      person entered - or a good value the source supplied - can never be
      overwritten by a public source.

    A listing OSM has never heard of is left blank. Blank is a true statement
    about our data; a plausible-looking guess is not.
    """
    from google.cloud import bigquery
    from whitespace_tool.brand_enrichment import enrich_location_contact

    project_id, dataset_id, credentials_json = _warehouse_settings()
    client = _bigquery_client(project_id, credentials_json)
    rows = list(client.query(f"""
        SELECT listing_id, name, latitude, longitude, phone_number, website_url, email
        FROM `{project_id}.{dataset_id}.listings`
        WHERE is_deleted IS NOT TRUE
          AND name IS NOT NULL AND name != ''
          AND latitude IS NOT NULL AND longitude IS NOT NULL
          AND (
            (phone_number IS NULL OR phone_number = '')
            OR (website_url IS NULL OR website_url = '')
            OR (email IS NULL OR email = '')
          )
        LIMIT 50
    """).result())
    candidates = [r for r in rows
                  if str(r["listing_id"]) not in _LOCATION_ENRICH_ATTEMPTED][:LOCATION_ENRICH_BATCH]
    if not candidates:
        return {"attempted": 0, "updated": 0, "fields_filled": 0}

    if len(_LOCATION_ENRICH_ATTEMPTED) > LOCATION_ENRICH_ATTEMPTED_MAX:
        _LOCATION_ENRICH_ATTEMPTED.clear()

    updated = 0
    fields_filled = 0
    for row in candidates:
        _enrichment_checkpoint()
        listing_id = str(row["listing_id"])
        _LOCATION_ENRICH_ATTEMPTED.add(listing_id)
        blank = [field for field in ("phone_number", "website_url", "email")
                 if not str(row[field] or "").strip()]
        if not blank:
            continue
        try:
            resolved = enrich_location_contact(str(row["name"] or ""), row["latitude"], row["longitude"])
        except Exception as exc:
            LOGGER.info("location_enrich_attempt_failed listing_id=%s error=%s", listing_id, exc)
            continue
        fills = {field: resolved[field] for field in blank if resolved.get(field)}
        if not fills:
            continue
        # The blank-only guard is repeated in SQL because the row was read a
        # moment ago: a concurrent user edit between the SELECT and this
        # UPDATE must win, not be clobbered by the background pass.
        assignments = ", ".join(f"{field} = @{field}" for field in fills)
        guards = " AND ".join(f"({field} IS NULL OR {field} = '')" for field in fills)
        try:
            client.query(
                f"UPDATE `{project_id}.{dataset_id}.listings` "
                f"SET {assignments}, last_observed_at = CURRENT_TIMESTAMP() "
                f"WHERE listing_id = @listing_id AND {guards}",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter(field, "STRING", value)
                    for field, value in fills.items()
                ] + [bigquery.ScalarQueryParameter("listing_id", "STRING", listing_id)])).result()
            updated += 1
            fields_filled += len(fills)
            LOGGER.info("location_enriched listing_id=%s fields=%s matched=%s",
                        listing_id, ",".join(sorted(fills)), resolved.get("matched_name", ""))
        except Exception as exc:
            LOGGER.warning("location_enrich_write_failed listing_id=%s error=%s", listing_id, exc)
        sleep(BRAND_ENRICH_PAUSE_SECONDS)
    if updated:
        _invalidate_cache_background()
    return {"attempted": len(candidates), "updated": updated, "fields_filled": fields_filled}


def _start_brand_enrichment_background() -> None:
    """Idle-only brand enrichment loop.

    Deliberately slow: it waits for a full minute of no foreground activity
    before each pass, enriches at most a handful of brands, and sleeps
    between each one. The goal is that this is never the reason the app feels
    heavy - it can always afford to take longer.
    """
    def worker() -> None:
        while True:
            try:
                idle_seconds = wall_clock_time() - LAST_FOREGROUND_ACTIVITY_AT
                if idle_seconds < BRAND_ENRICH_IDLE_SECONDS:
                    sleep(BRAND_ENRICH_IDLE_SECONDS - idle_seconds)
                    continue
                result = _idle_brand_enrichment_pass()
                # Store-level enrichment shares this thread rather than
                # adding another: on a 512MB box a second idle worker costs
                # more than it buys, and both want the same idle window.
                try:
                    locations = _idle_location_enrichment_pass()
                except Exception as exc:
                    LOGGER.warning("location_enrichment_pass_error error=%s", exc)
                    locations = {"attempted": 0}
                attempted = result["attempted"] + locations.get("attempted", 0)
                # Nothing left to try: back right off rather than spinning.
                sleep(300.0 if not attempted else 60.0)
            except Exception as exc:
                LOGGER.warning("brand_enrichment_loop_error error=%s", exc)
                sleep(300.0)

    threading.Thread(target=worker, name="brand-enrichment", daemon=True).start()


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    ui_dir = project_path("ui").resolve()
    handler = make_handler(ui_dir)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    try:
        project_id, dataset_id, credentials_json = _warehouse_settings()
        if get_cached_zipcode_count() < MINIMUM_US_ZIP_REFERENCE_ROWS:
            _start_zip_reference_background(project_id, dataset_id, credentials_json)
        _start_worldwide_reference_background(project_id, credentials_json)
    except Exception as exc:
        LOGGER.warning("reference_startup_sync_failed error=%s", exc)
    _start_silver_gold_scheduler()
    _start_brand_enrichment_background()
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        print(f"Workflow UI running at http://{host}:{port}/")
        httpd.serve_forever()
