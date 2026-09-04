from __future__ import annotations

import json
from typing import Any

from whitespace_tool.source_adapters.json_source import preview as preview_json


def validate_result(value: Any) -> Any:
    """Validate the value produced by a Python Editor script."""
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Python Editor result must be JSON-compatible") from exc
    if not isinstance(value, (list, dict)):
        raise ValueError("Python Editor result must be a JSON object or list")
    return value


def preview(content: bytes, record_path: str | None = None) -> dict[str, Any]:
    """Preview JSON emitted by the browser Python runtime."""
    payload = json.loads(content.decode("utf-8"))
    validate_result(payload)
    return preview_json(content, record_path)