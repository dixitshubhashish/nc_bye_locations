from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Generator

LOGGER = logging.getLogger("whitespace_tool.sqlite_cache")

DB_PATH = Path(__file__).resolve().parent.parent / ".cache" / "whitespace_cache.db"

# Columns mirrored locally from the gold layer's two master views, so
# reporting can filter/aggregate against SQLite instead of a live BigQuery
# round trip per query. Kept in one place since the write side (replace_gold_mirror)
# and read side (fetch_mirror_*) must agree on shape.
MIRROR_ZIP_BRAND_COLUMNS = (
    "zip_code", "state_code", "state_name", "county", "city_name", "population",
    "median_household_income", "median_age", "latitude", "longitude", "brand_name",
    "location_count", "last_observed_at",
)
MIRROR_LOCATION_COLUMNS = (
    "listing_id", "business_id", "brand", "name", "address", "city_name", "state_code",
    "state_name", "county", "zip_code", "phone_number", "latitude", "longitude",
    "coordinate_source", "coordinate_confidence", "country", "last_observed_at",
    "population", "median_household_income", "median_age",
)
MIRROR_BUSINESS_COLUMNS = ("business_id", "name")


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
        # Local mirror of the gold layer's two master views (vw_zip_brand_activity,
        # vw_reporting_locations) plus active businesses, refreshed by
        # sync_gold_mirror() after every silver+gold rebuild. Lets reporting_summary()
        # filter/aggregate locally instead of a live BigQuery round trip per query.
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS mirror_zip_brand_activity (
                {", ".join(f"{col} TEXT" if col not in ("population", "median_household_income", "median_age", "latitude", "longitude", "location_count") else f"{col} REAL" for col in MIRROR_ZIP_BRAND_COLUMNS)}
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mirror_zip_brand_geo ON mirror_zip_brand_activity (state_code, county, city_name, zip_code);")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS mirror_reporting_locations (
                {", ".join(f"{col} TEXT" if col not in ("latitude", "longitude", "coordinate_confidence", "population", "median_household_income", "median_age") else f"{col} REAL" for col in MIRROR_LOCATION_COLUMNS)}
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mirror_locations_geo ON mirror_reporting_locations (state_code, county, city_name, zip_code);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mirror_locations_brand ON mirror_reporting_locations (brand);")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mirror_businesses (
                business_id TEXT PRIMARY KEY,
                name TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mirror_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                synced_at TIMESTAMP,
                zip_brand_rows INTEGER,
                location_rows INTEGER,
                business_rows INTEGER
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


def _normalize_mirror_value(value: Any) -> Any:
    """BigQuery TIMESTAMP columns come back as datetime objects; SQLite has
    no native datetime type, so store everything as text/number/None."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def replace_gold_mirror(
    zip_brand_rows: list[dict[str, Any]],
    location_rows: list[dict[str, Any]],
    business_rows: list[dict[str, Any]],
) -> None:
    """Atomically replace the entire local mirror with a fresh snapshot from
    BigQuery. Called by sync_gold_mirror() right after every gold rebuild."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM mirror_zip_brand_activity")
            conn.executemany(
                f"INSERT INTO mirror_zip_brand_activity ({', '.join(MIRROR_ZIP_BRAND_COLUMNS)}) "
                f"VALUES ({', '.join(':' + c for c in MIRROR_ZIP_BRAND_COLUMNS)})",
                [{c: _normalize_mirror_value(row.get(c)) for c in MIRROR_ZIP_BRAND_COLUMNS} for row in zip_brand_rows],
            )
            conn.execute("DELETE FROM mirror_reporting_locations")
            conn.executemany(
                f"INSERT INTO mirror_reporting_locations ({', '.join(MIRROR_LOCATION_COLUMNS)}) "
                f"VALUES ({', '.join(':' + c for c in MIRROR_LOCATION_COLUMNS)})",
                [{c: _normalize_mirror_value(row.get(c)) for c in MIRROR_LOCATION_COLUMNS} for row in location_rows],
            )
            conn.execute("DELETE FROM mirror_businesses")
            conn.executemany(
                "INSERT INTO mirror_businesses (business_id, name) VALUES (:business_id, :name)",
                [{c: _normalize_mirror_value(row.get(c)) for c in MIRROR_BUSINESS_COLUMNS} for row in business_rows],
            )
            conn.execute(
                "INSERT OR REPLACE INTO mirror_meta (id, synced_at, zip_brand_rows, location_rows, business_rows) "
                "VALUES (1, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), len(zip_brand_rows), len(location_rows), len(business_rows)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_mirror_status() -> dict[str, Any] | None:
    """None means the mirror has never been synced (fresh install / gold
    not built yet) - callers should fall back to live BigQuery. Once
    synced, an empty result set is a legitimate answer, not a fallback
    trigger."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT synced_at, zip_brand_rows, location_rows, business_rows FROM mirror_meta WHERE id = 1").fetchone()
        if not row or not row["synced_at"]:
            return None
        return dict(row)


def _mirror_geo_filter_sql(state: str, county: str, city: str, zip_code: str) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if state:
        clauses.append("UPPER(state_code) = ?")
        params.append(state.upper())
    if county:
        clauses.append("LOWER(COALESCE(county, '')) = ?")
        params.append(county.lower())
    if city:
        clauses.append("LOWER(COALESCE(city_name, '')) = ?")
        params.append(city.lower())
    if zip_code:
        clauses.append("zip_code = ?")
        params.append(zip_code)
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def fetch_mirror_zip_brand_activity(state: str = "", county: str = "", city: str = "", zip_code: str = "") -> list[dict[str, Any]]:
    """Geo-filtered only - brand/demographic filtering happens in Python
    since callers need both a brand-filtered view (base/totals) and an
    unfiltered-by-brand view (gap analysis needs the full brand universe
    per zip) from the same fetch."""
    where_sql, params = _mirror_geo_filter_sql(state, county, city, zip_code)
    with get_db_connection() as conn:
        rows = conn.execute(f"SELECT * FROM mirror_zip_brand_activity WHERE 1=1{where_sql}", params).fetchall()
        return [dict(row) for row in rows]


def fetch_mirror_reporting_locations(state: str = "", county: str = "", city: str = "", zip_code: str = "") -> list[dict[str, Any]]:
    where_sql, params = _mirror_geo_filter_sql(state, county, city, zip_code)
    with get_db_connection() as conn:
        rows = conn.execute(f"SELECT * FROM mirror_reporting_locations WHERE 1=1{where_sql}", params).fetchall()
        return [dict(row) for row in rows]


def fetch_mirror_reporting_locations_by_brand(selected_brands: list[str]) -> list[dict[str, Any]]:
    """No geo filter - data_quality_summary is computed over the full
    (brand-filtered only) dataset, matching the BigQuery data_quality_query."""
    with get_db_connection() as conn:
        if not selected_brands:
            rows = conn.execute("SELECT * FROM mirror_reporting_locations").fetchall()
        else:
            placeholders = ", ".join("?" for _ in selected_brands)
            rows = conn.execute(f"SELECT * FROM mirror_reporting_locations WHERE brand IN ({placeholders})", selected_brands).fetchall()
        return [dict(row) for row in rows]


def fetch_mirror_businesses() -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT business_id, name FROM mirror_businesses").fetchall()]
