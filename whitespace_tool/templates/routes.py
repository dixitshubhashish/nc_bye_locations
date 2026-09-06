"""Template Library HTTP API dispatch.

Handles HTTP GET and POST request routing for template library endpoints.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from whitespace_tool.templates.services import (
    predefined_templates,
    list_templates,
    save_template_version,
)
import whitespace_tool.workflow_server as ws


def handle_templates_get(handler: Any) -> bool:
    """Dispatch a template library GET request.

    Returns True if handler.path matched a template endpoint, False otherwise.
    """
    path = handler.path

    if path == "/api/predefined-templates":
        try:
            ws._json_response(handler, 200, predefined_templates())
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    if path.startswith("/api/templates"):
        params = parse_qs(urlsplit(path).query)
        search = params.get("search", [""])[0]
        business_id = params.get("business_id", [""])[0]
        source_type_id = params.get("source_type_id", [""])[0]
        try:
            ws._json_response(handler, 200, list_templates(search, business_id, source_type_id))
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    return False


def handle_templates_post(handler: Any, payload: dict[str, Any]) -> bool:
    """Dispatch a template library POST request.

    Returns True if handled, False otherwise.
    """
    path = handler.path

    if path == "/api/templates/save":
        ws._json_response(handler, 200, save_template_version(payload))
        return True

    return False
