from __future__ import annotations

from pathlib import Path
from typing import Any

from whitespace_tool.models import ZipDemographics
from whitespace_tool.storage_config import load_storage_config


def _number(value: str) -> float | None:
    if value in (None, "", "-666666666", "-888888888", "-999999999"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _row_value(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    return row[field]


def fetch_bigquery_demographics(
    project_id: str,
    query: str,
    source_name: str,
    credentials_json: str | None = None,
) -> dict[str, ZipDemographics]:
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("Install google-cloud-bigquery and google-auth to query BigQuery demographics.") from exc

    if credentials_json:
        credentials = service_account.Credentials.from_service_account_file(credentials_json)
        client = bigquery.Client(project=project_id, credentials=credentials)
    else:
        client = bigquery.Client(project=project_id)

    rows: dict[str, ZipDemographics] = {}
    for row in client.query(query).result():
        zip_code = str(_row_value(row, "zip_code")).zfill(5)[:5]
        rows[zip_code] = ZipDemographics(
            zip_code=zip_code,
            population=_number(_row_value(row, "population")),
            median_household_income=_number(_row_value(row, "median_household_income")),
            median_age=_number(_row_value(row, "median_age")),
            source=source_name,
            city=_row_value(row, "city") if "city" in row.keys() else None,
            county=_row_value(row, "county") if "county" in row.keys() else None,
            state_code=_row_value(row, "state_code") if "state_code" in row.keys() else None,
            state_name=_row_value(row, "state_name") if "state_name" in row.keys() else None,
            latitude=_number(_row_value(row, "latitude")) if "latitude" in row.keys() else None,
            longitude=_number(_row_value(row, "longitude")) if "longitude" in row.keys() else None,
            households=_number(_row_value(row, "households")) if "households" in row.keys() else None,
            income_per_capita=_number(_row_value(row, "income_per_capita")) if "income_per_capita" in row.keys() else None,
            poverty=_number(_row_value(row, "poverty")) if "poverty" in row.keys() else None,
            employed_population=_number(_row_value(row, "employed_population")) if "employed_population" in row.keys() else None,
            unemployed_population=_number(_row_value(row, "unemployed_population")) if "unemployed_population" in row.keys() else None,
            housing_units=_number(_row_value(row, "housing_units")) if "housing_units" in row.keys() else None,
        )
    return rows


def resolve_bigquery_connection(source: dict[str, Any], config: dict[str, Any]) -> tuple[str, str | None]:
    storage = load_storage_config()
    project_id = source.get("project_id") or storage.get("project_id")
    credentials_json = source.get("credentials_json") or storage.get("credentials_json")
    if not project_id:
        raise ValueError("BigQuery project_id is missing from the storage configuration")
    if source.get("credentials_json") and credentials_json and not Path(credentials_json).is_absolute():
        credentials_json = str(Path(config["_config_dir"]) / credentials_json)
    return str(project_id), credentials_json


def load_demographics(config: dict[str, Any]) -> dict[str, ZipDemographics]:
    source = config["demographics_source"]
    if source["type"] == "bigquery":
        project_id, credentials_json = resolve_bigquery_connection(source, config)
        return fetch_bigquery_demographics(
            project_id,
            source["query"],
            source.get("name", "bigquery_demographics"),
            credentials_json,
        )
    raise ValueError(f"Unsupported demographics source type: {source['type']}. Only BigQuery demographics are supported.")
