from __future__ import annotations

import json

from whitespace_tool.source_adapters.common import choose_json_records, find_record_arrays, preview_payload


def preview(content: bytes, record_path: str | None = None) -> dict:
    payload = json.loads(content.decode("utf-8-sig"))
    rows, resolved_path = choose_json_records(payload, record_path)
    result = preview_payload(rows, resolved_path)
    if isinstance(payload, list):
        record_paths = [""]
    else:
        record_paths = sorted({path for path, records in find_record_arrays(payload, max_depth=3) if any(isinstance(row, dict) for row in records)})
    result["record_paths"] = record_paths
    return result
