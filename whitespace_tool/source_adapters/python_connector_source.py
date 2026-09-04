from __future__ import annotations

import ast
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import urllib.request

from whitespace_tool.source_adapters.json_source import preview as preview_json


MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 30


def _literal(value: ast.AST, field_name: str) -> Any:
    try:
        return ast.literal_eval(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a Python literal") from exc


def _validated_options(call: ast.Call) -> tuple[str, dict[str, str], dict[str, str], float]:
    if len(call.args) != 1:
        raise ValueError("http.get requires exactly one URL argument")
    url = _literal(call.args[0], "URL")
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    options: dict[str, Any] = {"params": {}, "headers": {}, "timeout": 15}
    for keyword in call.keywords:
        if keyword.arg not in options:
            raise ValueError("http.get supports only params, headers, and timeout")
        options[keyword.arg] = _literal(keyword.value, keyword.arg)
    for name in ("params", "headers"):
        value = options[name]
        if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
            raise ValueError(f"{name} must be a dictionary of string keys and values")
    headers = options["headers"]
    if any(name.lower() in {"authorization", "cookie", "proxy-authorization"} for name in headers):
        raise ValueError("Use the GET API JSON source for authenticated requests")
    timeout = options["timeout"]
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT_SECONDS} seconds")
    return url, options["params"], headers, float(timeout)


def parse_request(code: str) -> tuple[str, dict[str, str], dict[str, str], float]:
    try:
        module = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"Python connector syntax error: {exc.msg}") from exc
    if len(module.body) != 1 or not isinstance(module.body[0], ast.FunctionDef):
        raise ValueError("Connector code must contain only def fetch():")
    function = module.body[0]
    if function.name != "fetch" or function.args.args or function.args.kwonlyargs or function.decorator_list:
        raise ValueError("Connector code must define fetch() with no arguments or decorators")
    statements = function.body
    call: ast.Call | None = None
    if len(statements) == 1 and isinstance(statements[0], ast.Return):
        expression = statements[0].value
        if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute) and expression.func.attr == "json":
            call = expression.func.value if isinstance(expression.func.value, ast.Call) else None
    elif len(statements) == 2 and isinstance(statements[0], ast.Assign) and isinstance(statements[1], ast.Return):
        assignment = statements[0]
        returned = statements[1].value
        if len(assignment.targets) == 1 and isinstance(assignment.targets[0], ast.Name) and isinstance(assignment.value, ast.Call):
            if isinstance(returned, ast.Call) and isinstance(returned.func, ast.Attribute) and returned.func.attr == "json":
                if isinstance(returned.func.value, ast.Name) and returned.func.value.id == assignment.targets[0].id:
                    call = assignment.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        raise ValueError("fetch() must return http.get(...).json()")
    if not isinstance(call.func.value, ast.Name) or call.func.value.id != "http" or call.func.attr != "get":
        raise ValueError("fetch() may only call http.get(...).json()")
    return _validated_options(call)


def _validate_public_https_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Connector URLs must use HTTPS and include a public hostname")
    try:
        addresses = {ipaddress.ip_address(parsed.hostname)}
    except ValueError:
        if parsed.hostname.lower() == "localhost":
            raise ValueError("Connector URLs cannot target localhost or private networks")
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise ValueError("Connector hostname could not be resolved") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Connector URLs cannot target localhost or private networks")


def preview(code: str, record_path: str | None = None) -> dict[str, Any]:
    url, params, headers, timeout = parse_request(code)
    _validate_public_https_url(url)
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    request_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    request = urllib.request.Request(request_url, headers={"Accept": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise ValueError(f"Connector response must be JSON. Received content-type: {content_type}")
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("Connector response exceeds the 5 MB limit")
    try:
        json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Connector response is not valid JSON") from exc
    return preview_json(content, record_path)