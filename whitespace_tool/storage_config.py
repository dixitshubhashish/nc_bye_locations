from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_STORAGE_CONFIG = Path("config/connections/storage.json")
ENV_FILE = Path(".env")


def load_dotenv(path: str | Path = ENV_FILE) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    with env_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _credentials_json_path_from_env() -> str | None:
    inline_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON") or os.environ.get("BIGQUERY_CREDENTIALS_JSON")
    if inline_json:
        credentials_path = Path(os.environ.get("BIGQUERY_CREDENTIALS_PATH", "/tmp/birdeye-bigquery-service-account.json"))
        credentials_path.parent.mkdir(parents=True, exist_ok=True)
        credentials_path.write_text(inline_json, encoding="utf-8")
        return str(credentials_path)
    return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("BIGQUERY_CREDENTIALS_FILE")


def _config_from_env() -> dict[str, Any]:
    return {
        "project_id": os.environ.get("BIGQUERY_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        "credentials_json": _credentials_json_path_from_env(),
        "bronze_dataset_id": os.environ.get("BIGQUERY_BRONZE_DATASET_ID") or os.environ.get("BRONZE_DATASET_ID"),
        "silver_dataset_id": os.environ.get("BIGQUERY_SILVER_DATASET_ID") or os.environ.get("SILVER_DATASET_ID"),
        "gold_dataset_id": os.environ.get("BIGQUERY_GOLD_DATASET_ID") or os.environ.get("GOLD_DATASET_ID"),
    }


def load_storage_config(path: str | Path = DEFAULT_STORAGE_CONFIG) -> dict[str, Any]:
    load_dotenv()
    config_path = Path(path).resolve()
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
    else:
        config = {}
    env_config = {key: value for key, value in _config_from_env().items() if value}
    config = {**config, **env_config}
    credentials_json = config.get("credentials_json")
    if credentials_json and not Path(credentials_json).is_absolute():
        config["credentials_json"] = str(config_path.parent / credentials_json)
    return config
