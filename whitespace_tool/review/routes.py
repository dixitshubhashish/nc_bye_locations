"""Review HTTP API dispatch.

Handles HTTP GET and POST request routing for error listings and record reprocessing endpoints.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from whitespace_tool.review.services import (
    list_rejected,
    count_error_listings,
    reprocess_rejected,
    error_listings_by_brand,
)
import whitespace_tool.workflow_server as ws


def handle_review_get(handler: Any) -> bool:
    """Dispatch a review GET request.

    Returns True if path matched a review endpoint, False otherwise.
    """
    path = handler.path

    if path.startswith("/api/rejected"):
        event_id = parse_qs(urlsplit(path).query).get("event_id", [""])[0]
        try:
            ws._json_response(handler, 200, list_rejected(event_id))
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    if path.startswith("/api/error-listings/count"):
        business_id = parse_qs(urlsplit(path).query).get("business_id", [""])[0]
        try:
            ws._json_response(handler, 200, {"count": count_error_listings(business_id)})
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
    if path.startswith("/api/error-listings/by-brand"):
        try:
            ws._json_response(handler, 200, error_listings_by_brand())
        except Exception as exc:
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    return False


def handle_review_post(handler: Any, payload: dict[str, Any]) -> bool:
    """Dispatch a review POST request.

    Returns True if handled, False otherwise.
    """
    path = handler.path

    if path == "/api/reprocess":
        ws._json_response(handler, 200, reprocess_rejected(payload))
        return True

    return False
