"""Reporting HTTP API dispatch.

Owns the request routing for the reporting endpoints, extracted from the
monolithic ``do_GET`` / ``do_POST`` in ``whitespace_tool.workflow_server``.

Compute lives in ``workflow_server`` and is referenced lazily through the
module object (``ws.<name>``) so that:

1. there is no import cycle (this module is imported *during* the
   ``workflow_server`` module load), and
2. ``unittest.mock.patch.object(workflow_server, ...)`` on a shared symbol
   still affects the code path, because lookup happens on the module at call
   time.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import whitespace_tool.workflow_server as ws


def handle_reporting_get(handler) -> bool:
    """Dispatch a reporting GET request.

    Returns ``True`` if ``handler.path`` matched a reporting endpoint (a
    response has then been written); ``False`` if the caller should keep
    looking for a matching route.
    """
    path = handler.path

    if path.startswith("/api/reporting"):
        try:
            ws._json_response(handler, 200, ws.reporting_summary(parse_qs(urlsplit(path).query)))
        except Exception as exc:  # noqa: BLE001 - mirrors original endpoint behavior
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    if path.startswith("/api/geo/options"):
        params = parse_qs(urlsplit(path).query)
        state = params.get("state", [""])[0]
        county = params.get("county", [""])[0]
        try:
            ws._json_response(handler, 200, ws.geo_options(state, county))
        except Exception as exc:  # noqa: BLE001
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    if path.startswith("/api/zips/search"):
        params = parse_qs(urlsplit(path).query)
        q = params.get("q", [""])[0]
        state = params.get("state", [""])[0]
        county = params.get("county", [""])[0]
        city = params.get("city", [""])[0]
        try:
            ws._json_response(handler, 200, ws.search_zips(q, state, county, city))
        except Exception as exc:  # noqa: BLE001
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    if path == "/api/sample/status":
        try:
            ws._json_response(handler, 200, ws.sample_dataset_status())
        except Exception as exc:  # noqa: BLE001
            ws._json_response(handler, 400, {"error": str(exc)})
        return True

    return False


def handle_reporting_post(handler, payload: dict) -> bool:
    """Dispatch a reporting POST request.

    Returns ``True`` if handled. Exceptions propagate to the caller's shared
    error handler, matching the original inline behavior.
    """
    path = handler.path

    if path == "/api/reporting/refresh":
        ws._json_response(handler, 200, ws.build_silver_layer())
        return True

    if path == "/api/sample/load":
        ws._json_response(handler, 200, ws.load_sample_dataset(bool(payload.get("reset"))))
        return True

    return False
