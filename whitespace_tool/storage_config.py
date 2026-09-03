from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_STORAGE_CONFIG = Path("config/connections/storage.json")


def load_storage_config(path: str | Path = DEFAULT_STORAGE_CONFIG) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    credentials_json = config.get("credentials_json")
    if credentials_json and not Path(credentials_json).is_absolute():
        config["credentials_json"] = str(config_path.parent / credentials_json)
    return config
