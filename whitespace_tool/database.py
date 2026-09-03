from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from whitespace_tool.models import LocationRecord, ZipDemographics


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS states (
    state_id INTEGER PRIMARY KEY,
    state_code TEXT NOT NULL UNIQUE,
    state_name TEXT
);

CREATE TABLE IF NOT EXISTS cities (
    city_id INTEGER PRIMARY KEY,
    city_name TEXT NOT NULL,
    state_id INTEGER NOT NULL REFERENCES states(state_id),
    UNIQUE(city_name, state_id)
);

CREATE TABLE IF NOT EXISTS us_zips (
    zip_code TEXT PRIMARY KEY,
    city_id INTEGER REFERENCES cities(city_id),
    state_id INTEGER REFERENCES states(state_id),
    city TEXT,
    county TEXT,
    state_code TEXT,
    state_name TEXT,
    latitude REAL,
    longitude REAL,
    population REAL,
    median_household_income REAL,
    median_age REAL,
    households REAL,
    income_per_capita REAL,
    poverty REAL,
    employed_population REAL,
    unemployed_population REAL,
    housing_units REAL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS brands (
    brand_id INTEGER PRIMARY KEY,
    brand_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS franchisees (
    franchisee_id INTEGER PRIMARY KEY,
    franchisee_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS restaurants (
    restaurant_id INTEGER PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(brand_id),
    location_key TEXT NOT NULL,
    name TEXT,
    address TEXT,
    city_id INTEGER REFERENCES cities(city_id),
    state_id INTEGER REFERENCES states(state_id),
    zip_code TEXT NOT NULL REFERENCES us_zips(zip_code),
    latitude REAL,
    longitude REAL,
    franchisee_id INTEGER REFERENCES franchisees(franchisee_id),
    first_observed_at TEXT,
    last_observed_at TEXT,
    UNIQUE(brand_id, location_key)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(restaurant_id),
    review_source TEXT NOT NULL,
    rating REAL,
    review_count INTEGER,
    observed_at TEXT NOT NULL,
    UNIQUE(restaurant_id, review_source, observed_at)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    analysis_run_id INTEGER PRIMARY KEY,
    run_name TEXT NOT NULL,
    subject_brand_id INTEGER NOT NULL REFERENCES brands(brand_id),
    config_json TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS whitespace_candidates (
    candidate_id INTEGER PRIMARY KEY,
    analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(analysis_run_id),
    zip_code TEXT NOT NULL REFERENCES us_zips(zip_code),
    whitespace_type TEXT NOT NULL,
    similarity_distance REAL NOT NULL,
    competitors_present TEXT,
    UNIQUE(analysis_run_id, zip_code)
);

CREATE TABLE IF NOT EXISTS source_observations (
    observation_id INTEGER PRIMARY KEY,
    restaurant_id INTEGER REFERENCES restaurants(restaurant_id),
    source_name TEXT NOT NULL,
    source_location_id TEXT,
    observed_at TEXT NOT NULL,
    raw_payload TEXT,
    UNIQUE(source_name, source_location_id, observed_at)
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _id(conn: sqlite3.Connection, table: str, id_column: str, unique_column: str, value: str) -> int:
    conn.execute(f"INSERT OR IGNORE INTO {table} ({unique_column}) VALUES (?)", (value,))
    row = conn.execute(f"SELECT {id_column} FROM {table} WHERE {unique_column} = ?", (value,)).fetchone()
    return int(row[id_column])


def _state_id(conn: sqlite3.Connection, state_code: str) -> int:
    return _id(conn, "states", "state_id", "state_code", state_code or "UNKNOWN")


def _city_id(conn: sqlite3.Connection, city_name: str, state_id: int) -> int:
    city_name = city_name or "UNKNOWN"
    conn.execute("INSERT OR IGNORE INTO cities (city_name, state_id) VALUES (?, ?)", (city_name, state_id))
    row = conn.execute(
        "SELECT city_id FROM cities WHERE city_name = ? AND state_id = ?",
        (city_name, state_id),
    ).fetchone()
    return int(row["city_id"])


def load_demographics(conn: sqlite3.Connection, demographics: dict[str, ZipDemographics]) -> None:
    for demo in demographics.values():
        conn.execute(
            """
            INSERT OR REPLACE INTO us_zips
            (
                zip_code, city, county, state_code, state_name, latitude, longitude,
                population, median_household_income, median_age, households,
                income_per_capita, poverty, employed_population, unemployed_population,
                housing_units, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                demo.zip_code,
                demo.city,
                demo.county,
                demo.state_code,
                demo.state_name,
                demo.latitude,
                demo.longitude,
                demo.population,
                demo.median_household_income,
                demo.median_age,
                demo.households,
                demo.income_per_capita,
                demo.poverty,
                demo.employed_population,
                demo.unemployed_population,
                demo.housing_units,
                demo.source,
            ),
        )


def load_restaurants(conn: sqlite3.Connection, locations: list[LocationRecord]) -> None:
    for loc in locations:
        brand_id = _id(conn, "brands", "brand_id", "brand_name", loc.brand)
        state_id = _state_id(conn, loc.state)
        city_id = _city_id(conn, loc.city, state_id)
        conn.execute(
            """
            INSERT OR IGNORE INTO us_zips (zip_code, city_id, state_id, source)
            VALUES (?, ?, ?, ?)
            """,
            (loc.zip5, city_id, state_id, "location_source_only"),
        )
        conn.execute(
            """
            INSERT INTO restaurants
            (brand_id, location_key, name, address, city_id, state_id, zip_code, latitude, longitude, first_observed_at, last_observed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(brand_id, location_key) DO UPDATE SET
                name = excluded.name,
                address = excluded.address,
                city_id = excluded.city_id,
                state_id = excluded.state_id,
                zip_code = excluded.zip_code,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                last_observed_at = excluded.last_observed_at
            """,
            (
                brand_id,
                loc.location_id,
                loc.name,
                loc.address,
                city_id,
                state_id,
                loc.zip5,
                loc.latitude,
                loc.longitude,
                loc.observed_at,
                loc.observed_at,
            ),
        )
        restaurant_id = conn.execute(
            "SELECT restaurant_id FROM restaurants WHERE brand_id = ? AND location_key = ?",
            (brand_id, loc.location_id),
        ).fetchone()["restaurant_id"]
        conn.execute(
            """
            INSERT OR IGNORE INTO source_observations
            (restaurant_id, source_name, source_location_id, observed_at, raw_payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (restaurant_id, loc.source, loc.location_id, loc.observed_at, json.dumps(loc.raw, sort_keys=True)),
        )
