from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_config(path: str) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise SystemExit(
            f"Missing {config_path}. Copy configuration/bigquery_connection.example.json "
            f"to {config_path}, then set your service account JSON path."
        )
    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    credentials_json = config.get("credentials_json")
    if credentials_json:
        credentials_path = Path(credentials_json)
        if not credentials_path.is_absolute():
            credentials_path = config_path.parent.parent / credentials_path
        config["credentials_json"] = str(credentials_path)
    return config


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

    query = config["query"]
    rows = list(client.query(query).result())
    print(f"Connection OK. Returned {len(rows)} rows.")
    for row in rows[:10]:
        print(dict(row.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Test BigQuery service account connection")
    parser.add_argument(
        "--config",
        default="configuration/bigquery_connection.json",
        help="Path to BigQuery connection config JSON",
    )
    args = parser.parse_args()
    run_query(load_config(args.config))


if __name__ == "__main__":
    main()
