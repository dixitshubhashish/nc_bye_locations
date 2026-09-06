"""HTTP Server Request Handler module for Workflow UI.

Provides ``make_handler()`` factory and ``MapperHandler`` request class
for static asset serving, static alias resolution, and REST API route dispatching.
"""
from __future__ import annotations

import http.server
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from whitespace_tool.auth import routes as auth_routes
from whitespace_tool.mapping import routes as mapping_routes
from whitespace_tool.reporting import routes as reporting_routes
from whitespace_tool.review import routes as review_routes
from whitespace_tool.system import routes as system_routes
from whitespace_tool.templates import routes as template_routes

LOGGER = logging.getLogger("whitespace_tool.workflow_server")


def _json_response(handler: http.server.BaseHTTPRequestHandler, status: int, data: dict[str, Any]) -> None:
    payload = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def make_handler(ui_dir: Path):
    class MapperHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ui_dir), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:
            if hasattr(auth_routes, "handle_auth_get") and auth_routes.handle_auth_get(self):
                return
            if mapping_routes.handle_mapping_get(self):
                return
            if review_routes.handle_review_get(self):
                return
            if template_routes.handle_templates_get(self):
                return
            if system_routes.handle_system_get(self):
                return
            if reporting_routes.handle_reporting_get(self):
                return

            static_aliases = {
                "/constants.js": "facades/constants.js",
                "/login-hotfix.js": "facades/login-hotfix.js",
                "/js/common.js": "facades/common.js",
                "/js/mapper.js": "facades/mapper.js",
                "/js/review.js": "facades/review.js",
                "/js/templates.js": "facades/templates.js",
                "/js/constants.js": "facades/constants.js",
            }
            raw_path = self.path.split("?")[0]
            if raw_path in static_aliases:
                target_file = ui_dir / static_aliases[raw_path]
                if target_file.exists():
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(target_file.read_bytes())
                    return

            super().do_GET()

        def do_POST(self) -> None:
            if self.path not in {
                "/api/login", "/api/preview", "/api/source-url", "/api/sheets",
                "/api/save", "/api/clear", "/api/brands", "/api/learning",
                "/api/reprocess", "/api/field-alias", "/api/custom-field",
                "/api/custom-field/delete", "/api/templates/save",
                "/api/silver/enrich", "/api/reporting/refresh", "/api/sample/load"
            }:
                _json_response(self, 404, {"error": "Not found"})
                return
            request_id = uuid4().hex
            try:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not payload.get("event_id"):
                    payload["event_id"] = request_id
                LOGGER.info("request_started request_id=%s endpoint=%s content_length=%d", request_id, self.path, length)

                if reporting_routes.handle_reporting_post(self, payload):
                    return
                if auth_routes.handle_auth_post(self, payload):
                    return
                if mapping_routes.handle_mapping_post(self, payload):
                    return
                if review_routes.handle_review_post(self, payload):
                    return
                if template_routes.handle_templates_post(self, payload):
                    return
                if system_routes.handle_system_post(self, payload):
                    return
            except Exception as exc:
                LOGGER.exception("request_failed request_id=%s endpoint=%s error=%s", request_id, self.path, exc)
                _json_response(self, 400, {"error": str(exc), "request_id": request_id})

    return MapperHandler

