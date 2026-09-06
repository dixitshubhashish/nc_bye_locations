"""System Infrastructure HTTP API dispatch.

Handles HTTP GET and POST request routing for system health, storage, data clear, and medallion pipeline endpoints.
"""
from __future__ import annotations

from typing import Any

from whitespace_tool.system.storage import (
    ping_storage_connection,
    test_storage_connection,
    clear_saved_data,
)
from whitespace_tool.system.medallion import build_silver_layer
import whitespace_tool.workflow_server as ws


def handle_system_get(handler: Any) -> bool:
    """Dispatch a system GET request.

    Returns True if handler.path matched a system endpoint, False otherwise.
    """
    path = handler.path

    if path == "/api/ping":
        try:
            result = ping_storage_connection()
            result["timestamp"] = ws.utc_now_iso()
            ws._json_response(handler, 200, result)
        except Exception as exc:
            ws._json_response(handler, 400, {"ok": False, "status": "warming", "error": str(exc), "timestamp": ws.utc_now_iso()})
        return True

    if path == "/api/storage/test":
        try:
            ws._json_response(handler, 200, test_storage_connection())
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    return False


def handle_system_post(handler: Any, payload: dict[str, Any]) -> bool:
    """Dispatch a system POST request.

    Returns True if handled, False otherwise.
    """
    path = handler.path

    if path in {"/api/master/delete", "/api/data/clear"}:
        ws._json_response(handler, 200, ws.master_delete_data(payload))
        return True

    if path == "/api/silver/enrich":
        ws._json_response(handler, 200, build_silver_layer())
        return True

    return False
