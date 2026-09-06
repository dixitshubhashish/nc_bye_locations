"""Python connector source adapter for validating and previewing data produced by Python Editor scripts.

Ensures output from browser Python runtime connectors is JSON-compatible objects or lists
and delegates preview generation to JSON source adapter.
"""

from __future__ import annotations

import json
from typing import Any

from whitespace_tool.source_adapters.json_source import preview as preview_json


def validate_result(value: Any) -> Any:
    """Validate that the value produced by a Python Editor script is JSON-serializable.

    Args:
        value: Result produced by Python script.

    Returns:
        The validated value.

    Raises:
        ValueError: If result is not JSON-serializable or not a dict/list.
    """
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Python Editor result must be JSON-compatible") from exc
    if not isinstance(value, (list, dict)):
        raise ValueError("Python Editor result must be a JSON object or list")
    return value


def preview(content: bytes, record_path: str | None = None, fields_only: bool = False) -> dict[str, Any]:
    """Preview JSON bytes emitted by the Python connector execution.

    Args:
        content: Raw JSON bytes emitted by script.
        record_path: Optional explicit record array path.
        fields_only: If True, returns fields and sample rows without iterating full record set.

    Returns:
        Preview metadata dictionary.
    """
    payload = json.loads(content.decode("utf-8"))
    validate_result(payload)
    return preview_json(content, record_path, fields_only=fields_only)
