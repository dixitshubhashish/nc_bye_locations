from __future__ import annotations

import csv
import io

from whitespace_tool.source_preview.common import preview_payload


def preview(content: bytes, record_path: str | None = None) -> dict:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(row) for row in reader]
    return preview_payload(rows, record_path)
