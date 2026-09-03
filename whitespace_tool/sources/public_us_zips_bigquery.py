from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.cloud import bigquery
from google.oauth2 import service_account

from whitespace_tool.models import ZipDemographics
from whitespace_tool.sources.demographics import _number


DEFAULT_QUERY = """
SELECT
  z.zip_code,
  z.city,
  z.county,
  z.state_code,
  z.state_name,
  z.internal_point_lat AS latitude,
  z.internal_point_lon AS longitude,
  a.total_pop AS population,
  a.households,
  a.median_income AS median_household_income,
  a.income_per_capita,
  a.median_age,
  a.poverty,
  a.employed_pop AS employed_population,
  a.unemployed_pop AS unemployed_population,
  a.housing_units
FROM `bigquery-public-data.geo_us_boundaries.zip_codes` z
LEFT JOIN `bigquery-public-data.census_bureau_acs.zip_codes_2018_5yr` a
  ON z.zip_code = a.geo_id
WHERE z.zip_code IS NOT NULL
ORDER BY z.zip_code
"""


def _load_credentials(config_path: Path, config: dict[str, Any]):
    credentials_json = config.get("credentials_json")
    if not credentials_json:
        return None
    credentials_path = Path(credentials_json)
    if not credentials_path.is_absolute():
        credentials_path = config_path.parent.parent / credentials_path
    return service_account.Credentials.from_service_account_file(str(credentials_path))


def fetch_from_bigquery(config_path: str | Path, limit: int | None = None) -> dict[str, ZipDemographics]:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    query = config.get("public_us_zips_query") or DEFAULT_QUERY
    if limit:
        query = f"SELECT * FROM ({query}) LIMIT {int(limit)}"

    credentials = _load_credentials(path, config)
    client = bigquery.Client(project=config["project_id"], credentials=credentials)

    rows: dict[str, ZipDemographics] = {}
    for row in client.query(query).result():
        zip_code = str(row["zip_code"]).zfill(5)[:5]
        rows[zip_code] = ZipDemographics(
            zip_code=zip_code,
            population=_number(row["population"]),
            median_household_income=_number(row["median_household_income"]),
            median_age=_number(row["median_age"]),
            source="bigquery_public_geo_us_boundaries_join_acs_2018_5yr",
            city=row["city"],
            county=row["county"],
            state_code=row["state_code"],
            state_name=row["state_name"],
            latitude=_number(row["latitude"]),
            longitude=_number(row["longitude"]),
            households=_number(row["households"]),
            income_per_capita=_number(row["income_per_capita"]),
            poverty=_number(row["poverty"]),
            employed_population=_number(row["employed_population"]),
            unemployed_population=_number(row["unemployed_population"]),
            housing_units=_number(row["housing_units"]),
        )
    return rows
