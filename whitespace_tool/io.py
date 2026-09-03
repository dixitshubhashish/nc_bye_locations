from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as fh:
        if not fieldnames:
            return
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def write_demographics_csv(path: str | Path, rows: dict[str, Any]) -> None:
    output_rows = [
        {
            "zip_code": row.zip_code,
            "population": row.population,
            "median_household_income": row.median_household_income,
            "median_age": row.median_age,
            "city": row.city,
            "county": row.county,
            "state_code": row.state_code,
            "state_name": row.state_name,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "households": row.households,
            "income_per_capita": row.income_per_capita,
            "poverty": row.poverty,
            "employed_population": row.employed_population,
            "unemployed_population": row.unemployed_population,
            "housing_units": row.housing_units,
            "source": row.source,
        }
        for row in rows.values()
    ]
    write_csv(path, sorted(output_rows, key=lambda row: row["zip_code"]))
