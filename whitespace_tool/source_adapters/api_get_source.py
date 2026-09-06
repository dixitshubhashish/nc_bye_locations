"""HTTP GET API source adapter for reading JSON payloads from remote endpoints.

Provides utilities for formatting URL query parameters, authentication headers
(Bearer, Basic, API key), issuing HTTP requests, and delegating JSON parsing.
"""

from __future__ import annotations

import base64
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
import urllib.request

from whitespace_tool.source_adapters.json_source import preview as preview_json


def _clean_pairs(pairs: list[dict[str, str]] | None) -> dict[str, str]:
    """Clean and extract non-empty key-value pairs from a list of pair dictionaries.

    Args:
        pairs: List of dicts containing 'key' and 'value'.

    Returns:
        Dictionary of cleaned key-value pairs.
    """
    cleaned = {}
    for pair in pairs or []:
        key = str(pair.get("key", "")).strip()
        value = str(pair.get("value", "")).strip()
        if key:
            cleaned[key] = value
    return cleaned


def _url_with_query_params(url: str, query_params: list[dict[str, str]] | None) -> str:
    """Append query parameters to a URL, updating existing query strings if present.

    Args:
        url: Target endpoint URL.
        query_params: List of query parameter key-value pairs.

    Returns:
        Updated URL with appended query parameters.
    """
    params = _clean_pairs(query_params)
    if not params:
        return url
    parts = urlsplit(url)
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    existing.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(existing), parts.fragment))


def _auth_headers(auth: dict | None) -> dict[str, str]:
    """Generate authentication headers based on auth config.

    Args:
        auth: Authentication dictionary with 'type' and credentials.

    Returns:
        Dictionary of HTTP headers for authentication.
    """
    if not auth:
        return {}
    auth_type = auth.get("type", "none")
    if auth_type == "bearer":
        token = str(auth.get("token", "")).strip()
        return {"Authorization": f"Bearer {token}"} if token else {}
    if auth_type == "basic":
        username = str(auth.get("username", ""))
        password = str(auth.get("password", ""))
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
    if auth_type == "api_key_header":
        key_name = str(auth.get("key_name", "")).strip()
        key_value = str(auth.get("key_value", "")).strip()
        return {key_name: key_value} if key_name and key_value else {}
    return {}


def preview_url(
    url: str,
    record_path: str | None = None,
    headers: dict[str, str] | None = None,
    query_params: list[dict[str, str]] | None = None,
    auth: dict | None = None,
    fields_only: bool = False,
) -> dict:
    """Fetch JSON data from a URL using GET request and preview its records.

    Args:
        url: Remote endpoint URL.
        record_path: Optional path to record array in JSON response.
        headers: Additional HTTP headers.
        query_params: URL query parameters.
        auth: Authentication config dict.
        fields_only: If True, returns fields and sample rows without processing full record array.

    Returns:
        Preview dictionary of records.

    Raises:
        ValueError: If response is not JSON.
    """
    request_url = _url_with_query_params(url, query_params)
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    request_headers.update(_auth_headers(auth))
    request = urllib.request.Request(request_url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise ValueError(f"GET API response must be JSON. Received content-type: {content_type}")
        return preview_json(response.read(), record_path, fields_only=fields_only)

