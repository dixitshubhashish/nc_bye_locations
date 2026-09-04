from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Generator

LOGGER = logging.getLogger("whitespace_tool.sqlite_cache")

DB_PATH = Path(__file__).resolve().parent.parent / ".cache" / "whitespace_cache.db"


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_sqlite_cache() -> None:
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS us_zipcodes (
                zip_code TEXT PRIMARY KEY,
                city_name TEXT,
                county TEXT,
                state_code TEXT,
                state_name TEXT,
                latitude REAL,
                longitude REAL,
                population REAL,
                median_household_income REAL,
                median_age REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS field_catalogs (
                slug TEXT PRIMARY KEY,
                business_id TEXT,
                label TEXT NOT NULL,
                data_type TEXT NOT NULL,
                is_custom INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()


def cache_zipcodes(zip_records: list[dict[str, Any]]) -> None:
    if not zip_records:
        return
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO us_zipcodes (
                zip_code, city_name, county, state_code, state_name,
                latitude, longitude, population, median_household_income, median_age
            ) VALUES (
                :zip_code, :city_name, :county, :state_code, :state_name,
                :latitude, :longitude, :population, :median_household_income, :median_age
            );
        """, [
            {
                "zip_code": str(r.get("zip_code", "")).strip(),
                "city_name": r.get("city_name"),
                "county": r.get("county"),
                "state_code": r.get("state_code"),
                "state_name": r.get("state_name"),
                "latitude": float(r["latitude"]) if r.get("latitude") is not None else None,
                "longitude": float(r["longitude"]) if r.get("longitude") is not None else None,
                "population": float(r["population"]) if r.get("population") is not None else None,
                "median_household_income": float(r["median_household_income"]) if r.get("median_household_income") is not None else None,
                "median_age": float(r["median_age"]) if r.get("median_age") is not None else None,
            }
            for r in zip_records if r.get("zip_code")
        ])
        conn.commit()


def get_cached_zipcode(zip_code: str) -> dict[str, Any] | None:
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM us_zipcodes WHERE zip_code = ? LIMIT 1;", (zip_code.strip(),)).fetchone()
        if row:
            return dict(row)
    return None


def get_cached_query(cache_key: str) -> dict[str, Any] | None:
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT payload_json FROM query_cache WHERE cache_key = ? LIMIT 1;", (cache_key,)).fetchone()
        if row:
            try:
                return json.loads(row["payload_json"])
            except Exception:
                return None
    return None


def set_cached_query(cache_key: str, payload: dict[str, Any]) -> None:
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO query_cache (cache_key, payload_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP);",
            (cache_key, json.dumps(payload))
        )
        conn.commit()


def invalidate_cache(cache_key: str | None = None) -> None:
    init_sqlite_cache()
    with get_db_connection() as conn:
        if cache_key:
            conn.execute("DELETE FROM query_cache WHERE cache_key = ?;", (cache_key,))
        else:
            conn.execute("DELETE FROM query_cache;")
        conn.commit()
