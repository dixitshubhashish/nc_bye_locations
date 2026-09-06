from __future__ import annotations

import csv
import io

from whitespace_tool.source_adapters.common import preview_payload


def preview(content: bytes, record_path: str | None = None, fields_only: bool = False) -> dict:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # For lightweight field discovery, just get headers without processing rows
    if fields_only:
        # Estimate row count by counting newlines (excludes header)
        estimated_rows = text.count('\n') - 1 if '\n' in text else 0
        return {
            "record_path": record_path or "",
            "record_count": max(0, estimated_rows),
            "fields": [f for f in (reader.fieldnames or []) if f],
            "rows": [],
            "preview_rows": [],
        }

    rows = [dict(row) for row in reader]
    return preview_payload(rows, record_path)
