from __future__ import annotations

import json

from whitespace_tool.source_preview.common import choose_json_records, preview_payload


def preview(content: bytes, record_path: str | None = None) -> dict:
    payload = json.loads(content.decode("utf-8-sig"))
    rows, resolved_path = choose_json_records(payload, record_path)
    return preview_payload(rows, resolved_path)
