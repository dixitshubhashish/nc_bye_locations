from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "field_registry.json"


def load_field_registry() -> list[dict[str, Any]]:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)
