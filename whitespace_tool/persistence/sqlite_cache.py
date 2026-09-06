"""SQLite local cache and Gold mirror persistence storage.

Provides local SQLite storage for US zip code reference caching, reporting query payload
caching, and mirrored Gold layer BigQuery datasets for instant offline/fast reporting.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Generator

LOGGER = logging.getLogger("whitespace_tool.sqlite_cache")

DB_PATH = Path(__file__).resolve().parent.parent.parent / ".cache" / "whitespace_cache.db"

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


def _get_effective_db_path() -> Path:
    """Resolve active SQLite database file path, honoring module attribute overrides.

    Returns:
        Path instance pointing to active SQLite database file.
    """
    import sys
    default_path = Path(__file__).resolve().parent.parent.parent / ".cache" / "whitespace_cache.db"
    if DB_PATH != default_path:
        return DB_PATH
    root_mod = sys.modules.get("whitespace_tool.sqlite_cache")
    if root_mod and hasattr(root_mod, "DB_PATH") and getattr(root_mod, "DB_PATH") != default_path:
        return Path(getattr(root_mod, "DB_PATH"))
    return DB_PATH


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding an open SQLite connection with WAL journal mode.

    Yields:
        Configured sqlite3.Connection instance.
    """
    db_path = _get_effective_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_sqlite_cache() -> None:
    """Initialize SQLite database tables and indexes for cache and Gold mirror."""
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_listing_counts (
                business_id TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()


def cache_zipcodes(zip_records: list[dict[str, Any]]) -> None:
    """Insert or replace US ZIP code records in local SQLite cache.

    Args:
        zip_records: List of ZIP code record dictionaries.
    """
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
    """Retrieve a single ZIP code record from local SQLite cache.

    Args:
        zip_code: 5-digit postal code string.

    Returns:
        Row dictionary if found, None otherwise.
    """
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM us_zipcodes WHERE zip_code = ? LIMIT 1;", (zip_code.strip(),)).fetchone()
        if row:
            return dict(row)
    return None


def get_cached_query(cache_key: str) -> dict[str, Any] | None:
    """Retrieve a cached query response payload by cache key.

    Args:
        cache_key: Unique cache key string.

    Returns:
        Parsed JSON payload dict if found, None otherwise.
    """
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
    """Save a query response payload in the query_cache table.

    Args:
        cache_key: Cache key string.
        payload: JSON-serializable payload dictionary.
    """
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO query_cache (cache_key, payload_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP);",
            (cache_key, json.dumps(payload))
        )
        conn.commit()


def invalidate_cache(cache_key: str | None = None) -> None:
    """Clear query cache entries.

    Args:
        cache_key: Optional specific cache key to delete. If None, clear all cached queries.
    """
    init_sqlite_cache()
    with get_db_connection() as conn:
        if cache_key:
            conn.execute("DELETE FROM query_cache WHERE cache_key = ?;", (cache_key,))
        else:
            conn.execute("DELETE FROM query_cache;")
        conn.commit()


def get_error_count(business_id: str = "") -> int | None:
    """Return the last-known Review Error Listings count for a business, or None if not written."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT count FROM error_listing_counts WHERE business_id = ? LIMIT 1;",
            (business_id or "",),
        ).fetchone()
    return int(row["count"]) if row is not None else None


def set_error_count(business_id: str, count: int) -> None:
    """Persist a freshly-computed error count to SQLite cache."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO error_listing_counts (business_id, count, refreshed_at) VALUES (?, ?, CURRENT_TIMESTAMP);",
            (business_id or "", int(count)),
        )
        conn.commit()


def _normalize_mirror_value(value: Any) -> Any:
    """Normalize object values (such as ISO datetimes) for SQLite insertion.

    Args:
        value: Any input object.

    Returns:
        ISO formatted string if datetime, otherwise raw value.
    """
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def replace_gold_mirror(
    zip_brand_rows: list[dict[str, Any]],
    location_rows: list[dict[str, Any]],
    business_rows: list[dict[str, Any]],
) -> None:
    """Atomic full replace of local Gold layer SQLite mirror tables.

    Args:
        zip_brand_rows: Zip-brand activity view rows.
        location_rows: Reporting location view rows.
        business_rows: Business view rows.
    """
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
    """Fetch status and timestamp metadata for the local SQLite Gold mirror.

    Returns:
        Status dict if synced, None if uninitialized or unsynced.
    """
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT synced_at, zip_brand_rows, location_rows, business_rows FROM mirror_meta WHERE id = 1").fetchone()
        if not row or not row["synced_at"]:
            return None
        return dict(row)


def _mirror_geo_filter_sql(state: str, county: str, city: str, zip_code: str) -> tuple[str, list[Any]]:
    """Build SQL WHERE clause and parameter list for geographic filters.

    Args:
        state: State code filter string.
        county: County name filter string.
        city: City name filter string.
        zip_code: ZIP code filter string.

    Returns:
        Tuple of (WHERE SQL fragment, SQL parameters list).
    """
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
    """Fetch zip-brand activity rows from SQLite mirror applying geo filters.

    Args:
        state: State filter code.
        county: County filter name.
        city: City filter name.
        zip_code: ZIP code filter.

    Returns:
        List of matching zip-brand activity dictionary records.
    """
    where_sql, params = _mirror_geo_filter_sql(state, county, city, zip_code)
    with get_db_connection() as conn:
        rows = conn.execute(f"SELECT * FROM mirror_zip_brand_activity WHERE 1=1{where_sql}", params).fetchall()
        return [dict(row) for row in rows]


def fetch_mirror_reporting_locations(state: str = "", county: str = "", city: str = "", zip_code: str = "") -> list[dict[str, Any]]:
    """Fetch reporting store location rows from SQLite mirror applying geo filters.

    Args:
        state: State filter code.
        county: County filter name.
        city: City filter name.
        zip_code: ZIP code filter.

    Returns:
        List of matching store location records.
    """
    where_sql, params = _mirror_geo_filter_sql(state, county, city, zip_code)
    with get_db_connection() as conn:
        rows = conn.execute(f"SELECT * FROM mirror_reporting_locations WHERE 1=1{where_sql}", params).fetchall()
        return [dict(row) for row in rows]


def fetch_mirror_reporting_locations_by_brand(selected_brands: list[str]) -> list[dict[str, Any]]:
    """Fetch reporting store location rows filtered by selected brand names.

    Args:
        selected_brands: List of brand names to include. If empty, return all brands.

    Returns:
        List of brand-filtered store location records.
    """
    with get_db_connection() as conn:
        if not selected_brands:
            rows = conn.execute("SELECT * FROM mirror_reporting_locations").fetchall()
        else:
            placeholders = ", ".join("?" for _ in selected_brands)
            rows = conn.execute(f"SELECT * FROM mirror_reporting_locations WHERE brand IN ({placeholders})", selected_brands).fetchall()
        return [dict(row) for row in rows]


def fetch_mirror_businesses() -> list[dict[str, Any]]:
    """Fetch all business records from the SQLite mirror table.

    Returns:
        List of business records (business_id, name).
    """
    with get_db_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT business_id, name FROM mirror_businesses").fetchall()]
