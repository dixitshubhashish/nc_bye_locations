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
from logging.handlers import TimedRotatingFileHandler

from whitespace_tool.source_preview import api_get_source, csv_source, excel_source, json_source, xml_source
from whitespace_tool.data_validation import validate_source_row
from whitespace_tool.mapper import normalize_location
from whitespace_tool.models import utc_now_iso
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, build_table_rows, push_to_bigquery


SUPPORTED_SOURCE_TYPES = {"csv", "excel", "json", "xml", "api_get_json"}


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("whitespace_tool.mapper")
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
    event_id = str(payload.get("event_id") or uuid4().hex)
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
                "source_name": source_name,
                "row_number": index + 1,
                "errors": json.dumps(row_errors, sort_keys=True),
                "raw_record": json.dumps(row, sort_keys=True),
            })
        elif location is not None:
            locations.append(location)
    if not locations:
        raise ValueError(f"Mapper validation failed: no digestible rows; event_id={event_id}")

    warehouse_config = Path(os.environ.get("MAPPER_WAREHOUSE_CONFIG", "configs/demo.json"))
    with warehouse_config.open("r", encoding="utf-8") as handle:
        warehouse = json.load(handle).get("warehouse", {})
    project_id = warehouse.get("project_id")
    dataset_id = warehouse.get("dataset_id")
    credentials_json = warehouse.get("credentials_json")
    if credentials_json and not Path(credentials_json).is_absolute():
        credentials_json = str(warehouse_config.parent / credentials_json)
    if not project_id or not dataset_id:
        raise ValueError("BigQuery project_id and dataset_id are missing from the mapper warehouse config")

    mapper_id = f"mapper_{uuid4().hex}"
    config_json = _scrub_mapper(mapper)
    rows_by_table = build_table_rows(locations, {})
    rows_by_table["mapper_configs"] = [{
        "event_id": event_id,
        "mapper_id": mapper_id,
        "brand_name": mapper["brand"].strip(),
        "source_name": source_name,
        "source_type": mapper.get("source_type", "unknown"),
        "field_count": len(mapper["fields"]),
        "config_json": json.dumps(config_json, sort_keys=True),
        "created_at": utc_now_iso(),
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
    return {"event_id": event_id, "mapper_id": mapper_id, "mapped_rows": len(locations), "indigestible_rows": len(indigestible_records), "field_count": len(mapper["fields"]), "dataset": f"{project_id}.{dataset_id}"}


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
            super().do_GET()

        def do_POST(self) -> None:
            if self.path not in {"/api/preview", "/api/sheets", "/api/save"}:
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
        print(f"Mapper UI running at http://{host}:{port}/mapper.html")
        httpd.serve_forever()
