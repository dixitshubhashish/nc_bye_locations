from __future__ import annotations

import csv
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from whitespace_tool.models import ZipDemographics


ACS_VARIABLES = {
    "population": "B01003_001E",
    "median_household_income": "B19013_001E",
    "median_age": "B01002_001E",
}


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


def load_demographics_csv(path: str | Path, source_name: str) -> dict[str, ZipDemographics]:
    rows: dict[str, ZipDemographics] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            zip_code = str(row.get("zip_code", "")).zfill(5)[:5]
            if not zip_code:
                continue
            rows[zip_code] = ZipDemographics(
                zip_code=zip_code,
                population=_number(row.get("population", "")),
                median_household_income=_number(row.get("median_household_income", "")),
                median_age=_number(row.get("median_age", "")),
                source=source_name,
                city=row.get("city") or None,
                county=row.get("county") or None,
                state_code=row.get("state_code") or None,
                state_name=row.get("state_name") or None,
                latitude=_number(row.get("latitude", "")),
                longitude=_number(row.get("longitude", "")),
                households=_number(row.get("households", "")),
                income_per_capita=_number(row.get("income_per_capita", "")),
                poverty=_number(row.get("poverty", "")),
                employed_population=_number(row.get("employed_population", "")),
                unemployed_population=_number(row.get("unemployed_population", "")),
                housing_units=_number(row.get("housing_units", "")),
            )
    return rows


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


def fetch_acs_zcta(year: int, source_name: str = "census_acs5", api_key: str | None = None) -> dict[str, ZipDemographics]:
    variables = ",".join(ACS_VARIABLES.values())
    api_key = api_key or os.environ.get("CENSUS_API_KEY")
    params_payload = {"get": f"NAME,{variables}", "for": "zip code tabulation area:*"}
    if api_key:
        params_payload["key"] = api_key
    params = urllib.parse.urlencode(params_payload)
    url = f"https://api.census.gov/data/{year}/acs/acs5?{params}"
    with urllib.request.urlopen(url, timeout=60) as response:
        body = response.read().decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Census API did not return JSON. Set CENSUS_API_KEY or pass --api-key; "
                "recent Census API examples require an API key."
            ) from exc

    header = payload[0]
    indexes = {name: header.index(name) for name in header}
    rows: dict[str, ZipDemographics] = {}
    for raw in payload[1:]:
        zip_code = raw[indexes["zip code tabulation area"]].zfill(5)
        rows[zip_code] = ZipDemographics(
            zip_code=zip_code,
            population=_number(raw[indexes[ACS_VARIABLES["population"]]]),
            median_household_income=_number(raw[indexes[ACS_VARIABLES["median_household_income"]]]),
            median_age=_number(raw[indexes[ACS_VARIABLES["median_age"]]]),
            source=f"{source_name}_{year}",
        )
    return rows


def load_demographics(config: dict[str, Any]) -> dict[str, ZipDemographics]:
    source = config["demographics_source"]
    if source["type"] == "csv":
        path = Path(source["path"])
        if not path.is_absolute():
            path = Path(config["_config_dir"]) / path
        return load_demographics_csv(path, source["name"])
    if source["type"] == "census_acs5":
        return fetch_acs_zcta(int(source["year"]), source.get("name", "census_acs5"), source.get("api_key"))
    if source["type"] == "bigquery":
        credentials_json = source.get("credentials_json")
        if credentials_json:
            credentials_path = Path(credentials_json)
            if not credentials_path.is_absolute():
                credentials_json = str(Path(config["_config_dir"]) / credentials_path)
        return fetch_bigquery_demographics(
            source["project_id"],
            source["query"],
            source.get("name", "bigquery_demographics"),
            credentials_json,
        )
    raise ValueError(f"Unsupported demographics source type: {source['type']}")
