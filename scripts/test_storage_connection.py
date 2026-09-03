from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from whitespace_tool.storage_config import load_storage_config


def load_config(path: str) -> dict[str, Any]:
    try:
        return load_storage_config(path)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Missing {path}. Copy config/connections/storage.example.json to {path}, "
            "then set your service account JSON path."
        ) from exc


def run_query(config: dict[str, Any]) -> None:
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency. Install it with: python3 -m pip install google-cloud-bigquery google-auth"
        ) from exc

    project_id = config["project_id"]
    credentials_json = config.get("credentials_json")
    if credentials_json:
        credentials = service_account.Credentials.from_service_account_file(credentials_json)
        client = bigquery.Client(project=project_id, credentials=credentials)
    else:
        client = bigquery.Client(project=project_id)

    query = config.get("connection_test_query", "SELECT 1 AS connection_test")
    rows = list(client.query(query).result())
    print(f"Connection OK. Returned {len(rows)} rows.")
    for row in rows[:10]:
        print(dict(row.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Test BigQuery service account connection")
    parser.add_argument(
        "--config",
        default="config/connections/storage.json",
        help="Path to BigQuery connection config JSON",
    )
    args = parser.parse_args()
    run_query(load_config(args.config))


if __name__ == "__main__":
    main()
