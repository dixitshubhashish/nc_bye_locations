from __future__ import annotations

from collections import Counter
from typing import Any


def _clean(value: Any) -> str:
    return "".join(character.lower() for character in str(value or "") if character.isalnum())


def suggest_from_templates(
    templates: list[dict[str, Any]],
    source_fields: list[str],
    source_type: str,
) -> dict[str, dict[str, Any]]:
    """Learn target-to-source choices from saved workflow templates."""
    available = {_clean(field): field for field in source_fields if str(field).strip()}
    votes: dict[str, Counter[str]] = {}
    for template in templates:
        components = template.get("components", {})
        if isinstance(components, str):
            try:
                import json
                components = json.loads(components)
            except (TypeError, ValueError):
                continue
        mapper = components.get("mapper", components) if isinstance(components, dict) else {}
        if mapper.get("source_type") and mapper["source_type"] != source_type:
            continue
        for target, source_path in mapper.get("fields", {}).items():
            if _clean(source_path) in available:
                votes.setdefault(target, Counter())[available[_clean(source_path)]] += 1

    suggestions: dict[str, dict[str, Any]] = {}
    for target, counts in votes.items():
        source_path, count = counts.most_common(1)[0]
        suggestions[target] = {"source": source_path, "uses": count}
    return suggestions
