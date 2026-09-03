from __future__ import annotations

import base64
import json
import http.server
import logging
import os
from pathlib import Path
import socketserver
from typing import Any
from uuid import uuid4
import re
from logging.handlers import TimedRotatingFileHandler

from whitespace_tool.source_adapters import api_get_source, csv_source, excel_source, json_source, xml_source
from whitespace_tool.data_validation import validate_source_row
from whitespace_tool.normalization import normalize_location
from whitespace_tool.models import utc_now_iso
from whitespace_tool.learning import suggest_from_templates
from whitespace_tool.sources.demographics import fetch_bigquery_demographics
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, build_table_rows, clear_dataset_tables, push_to_bigquery


SUPPORTED_SOURCE_TYPES = {"csv", "excel", "json", "xml", "api_get_json"}


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


def _json_response(handler: http.server.BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


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


def mapper_targets() -> list[dict[str, Any]]:
    return [
        {"table": table, "field": field["name"], "type": field["type"], "mode": field["mode"]}
        for table, fields in TABLE_SCHEMAS.items()
        for field in fields
    ]


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
    warehouse_config = Path(os.environ.get("WORKFLOW_CONFIG", "config/demo.json"))
    with warehouse_config.open("r", encoding="utf-8") as handle:
        warehouse = json.load(handle).get("warehouse", {})
    credentials_json = warehouse.get("credentials_json")
    if credentials_json and not Path(credentials_json).is_absolute():
        credentials_json = str(warehouse_config.parent / credentials_json)
    if not warehouse.get("project_id") or not warehouse.get("dataset_id"):
        raise ValueError("Storage project and dataset are missing from the configuration")
    return warehouse["project_id"], warehouse.get("bronze_dataset_id") or warehouse.get("dataset_id", ""), credentials_json


def _load_mapped_zip_demographics(zip_codes: set[str]) -> dict[str, Any]:
    config_path = Path(os.environ.get("WORKFLOW_CONFIG", "config/demo.json"))
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    source = config.get("demographics_source", {})
    if source.get("type") != "bigquery" or not zip_codes:
        return {}
    credentials_json = source.get("credentials_json")
    if credentials_json and not Path(credentials_json).is_absolute():
        credentials_json = str(config_path.parent / credentials_json)
    quoted_zips = ", ".join(f"'{zip_code}'" for zip_code in sorted(zip_codes))
    query = f"SELECT * FROM ({source['query'].rstrip(';')}) AS public_zips WHERE zip_code IN ({quoted_zips})"
    LOGGER.info("zip_lookup_started source=%s zip_count=%d", source.get("name", "public_demographics"), len(zip_codes))
    demographics = fetch_bigquery_demographics(
        source["project_id"], query, source.get("name", "public_demographics"), credentials_json
    )
    LOGGER.info("zip_lookup_succeeded requested=%d matched=%d", len(zip_codes), len(demographics))
    return demographics


def _bigquery_client(project_id: str, credentials_json: str | None):
    from google.cloud import bigquery
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(credentials_json) if credentials_json else None
    return bigquery.Client(project=project_id, credentials=credentials)


def _ensure_dataset(client: Any, project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery

    client.create_dataset(bigquery.Dataset(f"{project_id}.{dataset_id}"), exists_ok=True)


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
    query = f"SELECT business_id, name, slug, website_url, status FROM `{project_id}.{dataset_id}.businesses` WHERE @search = '' OR LOWER(name) LIKE CONCAT('%', LOWER(@search), '%') ORDER BY name LIMIT 100"
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
    lookup = f"SELECT business_id, name, slug, website_url, status FROM `{project_id}.{dataset_id}.businesses` WHERE slug = @slug ORDER BY created_at DESC LIMIT 1"
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
    business_id = str(mapper.get("business_id", "")).strip()
    if not business_id:
        raise ValueError("Select an existing business or create a new business before saving")
    event_id = str(payload.get("event_id") or uuid4().hex)
    mapper["business_id"] = business_id
    mapper["source_type_id"] = source_type_id
    locations = []
    indigestible_records = []
    for index, row in enumerate(rows):
        row_errors = validate_source_row(row, mapper)
        location = normalize_location(row, mapper, source_name, index)
        if location is None:
            row_errors.append({"field": "required_location", "reason": "missing brand or ZIP Code"})
        elif any(not str(getattr(location, field) or "").strip() for field in REQUIRED_LOCATION_VALUES):
            row_errors.append({"field": "required_location", "reason": "missing mandatory value"})
        if row_errors:
            indigestible_records.append({
                "event_id": event_id,
                "source_type_id": source_type_id,
                "row_number": index + 1,
                "errors": json.dumps(row_errors, sort_keys=True),
                "raw_record": json.dumps(row, sort_keys=True),
            })
        elif location is not None:
            locations.append(location)
    project_id, dataset_id, credentials_json = _warehouse_settings()

    mapper_id = f"mapper_{uuid4().hex}"
    config_json = _scrub_mapper(mapper)
    demographics = _load_mapped_zip_demographics({location.zip5 for location in locations})
    rows_by_table = build_table_rows(locations, demographics)
    rows_by_table["businesses"] = []
    for record in indigestible_records:
        record["source_type_id"] = source_type_id
    rows_by_table["source_types"] = []
    rows_by_table["workflow_templates"] = [{
        "workflow_template_id": str(uuid4()),
        "business_id": business_id, "name": source_name,
        "components": json.dumps({"mapper": mapper, "source_type_id": source_type_id}, sort_keys=True),
        "archived_components": None, "created_at": utc_now_iso(), "updated_at": utc_now_iso(),
    }]
    rows_by_table["indigestible_records"] = indigestible_records
    push_to_bigquery(project_id, dataset_id, rows_by_table, credentials_json)
    LOGGER.info(
        "save_succeeded mapper_id=%s dataset=%s mapped_rows=%d mapped_fields=%d",
        mapper_id,
        f"{project_id}.{dataset_id}",
        len(locations),
        len(mapper["fields"]),
    )
    return {"event_id": event_id, "mapper_id": mapper_id, "total_rows": len(rows), "mapped_rows": len(locations), "indigestible_rows": len(indigestible_records), "field_count": len(mapper["fields"]), "dataset": f"{project_id}.{dataset_id}"}


def clear_saved_data() -> dict[str, Any]:
    warehouse_config = Path(os.environ.get("WORKFLOW_CONFIG", "config/demo.json"))
    with warehouse_config.open("r", encoding="utf-8") as handle:
        warehouse = json.load(handle).get("warehouse", {})
    project_id = warehouse.get("project_id")
    dataset_id = warehouse.get("dataset_id")
    credentials_json = warehouse.get("credentials_json")
    if credentials_json and not Path(credentials_json).is_absolute():
        credentials_json = str(warehouse_config.parent / credentials_json)
    if not project_id or not dataset_id:
        raise ValueError("Storage project and dataset are missing from the configuration")
    deleted = clear_dataset_tables(project_id, dataset_id, credentials_json)
    return {"dataset": f"{project_id}.{dataset_id}", "deleted_tables": deleted, "deleted_count": len(deleted)}


def make_handler(ui_dir: Path):
    class MapperHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ui_dir), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:
            if self.path == "/api/schema":
                _json_response(self, 200, {"targets": mapper_targets()})
                return
            if self.path.startswith("/api/brands"):
                from urllib.parse import parse_qs, urlsplit
                search = parse_qs(urlsplit(self.path).query).get("search", [""])[0]
                try:
                    _json_response(self, 200, list_brands(search))
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            super().do_GET()

        def do_POST(self) -> None:
            if self.path not in {"/api/preview", "/api/sheets", "/api/save", "/api/clear", "/api/brands", "/api/learning"}:
                _json_response(self, 404, {"error": "Not found"})
                return
            request_id = uuid4().hex
            try:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                payload["event_id"] = request_id
                LOGGER.info("request_started request_id=%s endpoint=%s content_length=%d", request_id, self.path, length)
                if self.path == "/api/sheets":
                    _json_response(self, 200, source_sheets(payload))
                elif self.path == "/api/save":
                    _json_response(self, 200, save_mapper(payload))
                elif self.path == "/api/clear":
                    _json_response(self, 200, clear_saved_data())
                elif self.path == "/api/brands":
                    _json_response(self, 200, create_brand(payload))
                elif self.path == "/api/learning":
                    _json_response(self, 200, learn_mappings(payload))
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
        print(f"Workflow UI running at http://{host}:{port}/workflow_templates.html")
        httpd.serve_forever()
