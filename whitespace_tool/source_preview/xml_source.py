from __future__ import annotations

from typing import Any
from xml.etree import ElementTree

from whitespace_tool.source_preview.common import preview_payload


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_to_dict(element: ElementTree.Element) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in element.attrib.items():
        row[f"@{key}"] = value
    children = list(element)
    if children:
        for child in children:
            key = _strip_namespace(child.tag)
            child_value = _element_to_dict(child) if list(child) or child.attrib else (child.text or "").strip()
            if key in row:
                if not isinstance(row[key], list):
                    row[key] = [row[key]]
                row[key].append(child_value)
            else:
                row[key] = child_value
    text = (element.text or "").strip()
    if text and not children:
        row["text"] = text
    return row


def _find_repeating_records(root: ElementTree.Element) -> tuple[list[ElementTree.Element], str]:
    groups: dict[tuple[str, str], list[ElementTree.Element]] = {}
    for parent in root.iter():
        for child in list(parent):
            tag = _strip_namespace(child.tag)
            groups.setdefault((_strip_namespace(parent.tag), tag), []).append(child)
    candidates = [items for items in groups.values() if len(items) > 1]
    if not candidates:
        return [root], _strip_namespace(root.tag)
    records = max(candidates, key=len)
    return records, _strip_namespace(records[0].tag)


def preview(content: bytes, record_path: str | None = None) -> dict:
    root = ElementTree.fromstring(content.decode("utf-8-sig"))
    records, resolved_path = _find_repeating_records(root)
    rows = [_element_to_dict(record) for record in records]
    return preview_payload(rows, record_path or resolved_path)
