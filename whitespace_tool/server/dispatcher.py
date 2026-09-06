"""API Route Dispatcher & Endpoint Registry module.

Maps incoming REST endpoints (/api/*) to domain route handlers.
"""
from __future__ import annotations

import logging
from typing import Any

from whitespace_tool.auth import routes as auth_routes
from whitespace_tool.mapping import routes as mapping_routes
from whitespace_tool.reporting import routes as reporting_routes
from whitespace_tool.review import routes as review_routes
from whitespace_tool.system import routes as system_routes
from whitespace_tool.templates import routes as template_routes

LOGGER = logging.getLogger("whitespace_tool.workflow_server")

SUPPORTED_POST_ENDPOINTS = {
    "/api/login", "/api/preview", "/api/source-url", "/api/sheets",
    "/api/save", "/api/clear", "/api/brands", "/api/learning",
    "/api/reprocess", "/api/field-alias", "/api/custom-field",
    "/api/custom-field/delete", "/api/templates/save",
    "/api/silver/enrich", "/api/reporting/refresh", "/api/sample/load"
}


def dispatch_get_request(handler: Any) -> bool:
    if hasattr(auth_routes, "handle_auth_get") and auth_routes.handle_auth_get(handler):
        return True
    if mapping_routes.handle_mapping_get(handler):
        return True
    if review_routes.handle_review_get(handler):
        return True
    if template_routes.handle_templates_get(handler):
        return True
    if system_routes.handle_system_get(handler):
        return True
    if reporting_routes.handle_reporting_get(handler):
        return True
    return False


def dispatch_post_request(handler: Any, payload: dict[str, Any]) -> bool:
    if reporting_routes.handle_reporting_post(handler, payload):
        return True
    if auth_routes.handle_auth_post(handler, payload):
        return True
    if mapping_routes.handle_mapping_post(handler, payload):
        return True
    if review_routes.handle_review_post(handler, payload):
        return True
    if template_routes.handle_templates_post(handler, payload):
        return True
    if system_routes.handle_system_post(handler, payload):
        return True
    return False

