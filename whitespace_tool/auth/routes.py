"""Authentication HTTP API dispatch.

Handles HTTP POST request routing for authentication endpoints.
"""
from __future__ import annotations

from typing import Any
from whitespace_tool.auth.services import authenticate
import whitespace_tool.workflow_server as ws


def handle_auth_post(handler: Any, payload: dict[str, Any]) -> bool:
    """Dispatch an authentication POST request.

    Args:
        handler: The HTTP request handler instance.
        payload: Parsed JSON request payload.

    Returns:
        True if the endpoint was handled, False otherwise.
    """
    path = handler.path

    if path == "/api/login":
        ws._json_response(handler, 200, authenticate(payload))
        return True

    return False
