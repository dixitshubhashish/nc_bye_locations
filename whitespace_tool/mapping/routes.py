"""Mapping HTTP API dispatch.

Handles HTTP GET and POST request routing for mapping, source, brand, and catalog endpoints.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from whitespace_tool.mapping.catalog import (
    mapper_targets_with_status,
    add_field_alias,
    create_custom_field,
    delete_custom_field,
)
from whitespace_tool.mapping.sources import (
    preview_source,
    source_sheets,
    fetch_public_source,
    dominos_source,
    list_brands,
    create_brand,
    list_source_types,
    prepare_zipcodes,
)
from whitespace_tool.mapping.ingestion import (
    save_mapper,
    learn_mappings,
)
import whitespace_tool.workflow_server as ws


def handle_mapping_get(handler: Any) -> bool:
    """Dispatch a mapping GET request.

    Returns True if handler.path matched a mapping endpoint, False otherwise.
    """
    path = handler.path

    if path == "/api/schema":
        result = mapper_targets_with_status()
        ws._json_response(
            handler, 200, {"targets": result["fields"], "source": result["source"], "warning": result.get("warning")}
        )
        return True

    if path == "/api/field-registry":
        result = mapper_targets_with_status()
        ws._json_response(handler, 200, result)
        return True

    if path == "/api/prepare":
        try:
            ws._json_response(handler, 200, prepare_zipcodes())
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    if path.startswith("/api/brands"):
        search = parse_qs(urlsplit(path).query).get("search", [""])[0]
        try:
            ws._json_response(handler, 200, list_brands(search))
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    if path == "/api/source-types":
        try:
            ws._json_response(handler, 200, list_source_types())
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    if path.startswith("/api/dominos-source"):
        params = parse_qs(urlsplit(path).query)
        try:
            raw_limit = params.get("limit", ["1"])[0]
            limit = None if raw_limit == "all" else int(raw_limit or "1")
            order_type = params.get("type", ["Delivery"])[0]
            raw_stores_per_zip = params.get("stores_per_zip", ["1"])[0]
            stores_per_zip = None if raw_stores_per_zip == "all" else int(raw_stores_per_zip or "1")
            max_workers = int(params.get("max_workers", ["8"])[0] or "8")
            one_per_zip = params.get("one_per_zip", ["false"])[0].lower() in {"1", "true", "yes"}
            provider = params.get("provider", ["auto"])[0]
            ws._json_response(
                handler, 200, dominos_source(limit, order_type, stores_per_zip, max_workers, one_per_zip, provider)
            )
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    return False


def handle_mapping_post(handler: Any, payload: dict[str, Any]) -> bool:
    """Dispatch a mapping POST request.

    Returns True if handled, False otherwise.
    """
    path = handler.path

    if path == "/api/source-url":
        ws._json_response(handler, 200, fetch_public_source(payload))
        return True
    if path == "/api/sheets":
        ws._json_response(handler, 200, source_sheets(payload))
        return True
    if path == "/api/save":
        ws._json_response(handler, 200, save_mapper(payload))
        return True
    if path == "/api/brands":
        ws._json_response(handler, 200, create_brand(payload))
        return True
    if path == "/api/brand/update":
        ws._json_response(handler, 200, ws.update_brand(payload))
        return True
    if path == "/api/brands/merge":
        ws._json_response(handler, 200, ws.merge_brands(payload))
        return True
    if path == "/api/learning":
        ws._json_response(handler, 200, learn_mappings(payload))
        return True
    if path == "/api/field-alias":
        ws._json_response(handler, 200, add_field_alias(payload))
        return True
    if path == "/api/custom-field":
        ws._json_response(handler, 200, create_custom_field(payload))
        return True
    if path == "/api/custom-field/delete":
        ws._json_response(handler, 200, delete_custom_field(payload))
        return True
    if path == "/api/preview":
        ws._json_response(handler, 200, preview_source(payload))
        return True

    return False
