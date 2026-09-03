from __future__ import annotations

import base64
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
import urllib.request

from whitespace_tool.source_preview.json_source import preview as preview_json


def _clean_pairs(pairs: list[dict[str, str]] | None) -> dict[str, str]:
    cleaned = {}
    for pair in pairs or []:
        key = str(pair.get("key", "")).strip()
        value = str(pair.get("value", "")).strip()
        if key:
            cleaned[key] = value
    return cleaned


def _url_with_query_params(url: str, query_params: list[dict[str, str]] | None) -> str:
    params = _clean_pairs(query_params)
    if not params:
        return url
    parts = urlsplit(url)
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    existing.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(existing), parts.fragment))


def _auth_headers(auth: dict | None) -> dict[str, str]:
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
) -> dict:
    request_url = _url_with_query_params(url, query_params)
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    request_headers.update(_auth_headers(auth))
    request = urllib.request.Request(request_url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise ValueError(f"GET API response must be JSON. Received content-type: {content_type}")
        return preview_json(response.read(), record_path)
