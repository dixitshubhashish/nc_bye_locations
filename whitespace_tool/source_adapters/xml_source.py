"""XML source adapter for converting XML structures into tabular row records.

Strips namespaces, recursively converts XML element nodes and attributes into dictionaries,
and automatically locates repeating record elements.
"""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree

from whitespace_tool.source_adapters.common import preview_payload


def _strip_namespace(tag: str) -> str:
    """Strip XML namespace string from element tag.

    Args:
        tag: Full XML tag name.

    Returns:
        Local tag name.
    """
    return tag.rsplit("}", 1)[-1]


def _element_to_dict(element: ElementTree.Element) -> dict[str, Any]:
    """Recursively convert an XML element tree into a dictionary representation.

    Args:
        element: ElementTree XML element.

    Returns:
        Dictionary representation of attributes, children, and text.
    """
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
    """Find repeating record elements under the XML root.

    Args:
        root: Root ElementTree element.

    Returns:
        Tuple of (list of record elements, record tag name).
    """
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


def preview(content: bytes, record_path: str | None = None, fields_only: bool = False) -> dict:
    """Parse XML content bytes and return structured row dictionaries.

    Args:
        content: XML content bytes.
        record_path: Optional explicit tag/path name override.
        fields_only: If True, returns fields and sample rows without processing all elements.

    Returns:
        Preview payload dictionary.
    """
    root = ElementTree.fromstring(content.decode("utf-8-sig"))
    records, resolved_path = _find_repeating_records(root)
    rows = [_element_to_dict(record) for record in records]
    return preview_payload(rows, record_path or resolved_path, fields_only=fields_only)
