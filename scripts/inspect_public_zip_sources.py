from __future__ import annotations

import json
from pathlib import Path

from google.cloud import bigquery
from google.oauth2 import service_account


CONFIG_PATH = Path("configuration/bigquery_connection.json")
TABLES = [
    "bigquery-public-data.geo_us_boundaries.zip_codes",
    "bigquery-public-data.census_bureau_acs.zip_codes_2018_5yr",
]


def main() -> None:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    credentials_path = Path(config["credentials_json"])
    if not credentials_path.is_absolute():
        credentials_path = CONFIG_PATH.parent.parent / credentials_path

    credentials = service_account.Credentials.from_service_account_file(str(credentials_path))
    client = bigquery.Client(project=config["project_id"], credentials=credentials)

    for table_name in TABLES:
        table = client.get_table(table_name)
        print(f"\n{table_name}")
        print(f"rows={table.num_rows}")
        for field in table.schema:
            print(f"{field.name}: {field.field_type}")


if __name__ == "__main__":
    main()
