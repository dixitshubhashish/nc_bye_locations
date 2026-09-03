from __future__ import annotations

import base64
import json
import http.server
from pathlib import Path
import socketserver
from typing import Any

from whitespace_tool.source_preview import api_get_source, csv_source, excel_source, json_source, xml_source
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS


SUPPORTED_SOURCE_TYPES = {"csv", "excel", "json", "xml", "api_get_json"}


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
            if self.path not in {"/api/preview", "/api/sheets"}:
                _json_response(self, 404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if self.path == "/api/sheets":
                    _json_response(self, 200, source_sheets(payload))
                else:
                    _json_response(self, 200, preview_source(payload))
            except Exception as exc:
                _json_response(self, 400, {"error": str(exc)})

    return MapperHandler


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    ui_dir = Path("ui").resolve()
    handler = make_handler(ui_dir)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), handler) as httpd:
        print(f"Mapper UI running at http://{host}:{port}/mapper.html")
        httpd.serve_forever()
