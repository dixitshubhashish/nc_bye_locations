from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Generator

from whitespace_tool.paths import project_path

LOGGER = logging.getLogger("whitespace_tool.sqlite_cache")

DB_PATH = project_path(".cache/whitespace_cache.db")

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
MIRROR_BUSINESS_COLUMNS = (
    "business_id", "name", "slug", "description", "logo_url", "website_url", "status",
    "created_at", "updated_at", "listing_count",
    "meta_title", "meta_description", "country_of_origin", "is_reference_data",
    "reference_key", "default_source_url", "default_source_name", "source_type_id",
    "source_type_name", "display_business_id",
)


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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_us_zipcodes_lat_lon ON us_zipcodes (latitude, longitude);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_us_zipcodes_state_city ON us_zipcodes (state_code, city_name);")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS worldwide_cities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country_code TEXT,
                country_name TEXT,
                state_name TEXT,
                state_code TEXT,
                district TEXT,
                city TEXT,
                town TEXT,
                zip_code TEXT,
                latitude REAL,
                longitude REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ww_cities_country_city ON worldwide_cities (country_code, city);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ww_cities_city ON worldwide_cities (city);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ww_cities_town ON worldwide_cities (town);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ww_cities_district ON worldwide_cities (district);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ww_cities_lat_lon ON worldwide_cities (latitude, longitude);")
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
                name TEXT,
                slug TEXT,
                description TEXT,
                logo_url TEXT,
                website_url TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                listing_count INTEGER,
                meta_title TEXT,
                meta_description TEXT,
                country_of_origin TEXT,
                is_reference_data INTEGER,
                reference_key TEXT,
                default_source_url TEXT,
                default_source_name TEXT,
                source_type_id TEXT,
                source_type_name TEXT,
                display_business_id TEXT
            );
        """)
        existing_business_columns = {row["name"] for row in conn.execute("PRAGMA table_info(mirror_businesses)").fetchall()}
        for column in MIRROR_BUSINESS_COLUMNS:
            if column not in existing_business_columns:
                column_type = "INTEGER" if column in {"is_reference_data", "listing_count"} else "TEXT"
                conn.execute(f"ALTER TABLE mirror_businesses ADD COLUMN {column} {column_type};")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mirror_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                synced_at TIMESTAMP,
                zip_brand_rows INTEGER,
                location_rows INTEGER,
                business_rows INTEGER
            );
        """)
        # Last-known Review Error Listings count, keyed by business_id
        # (empty string = the all-businesses total shown on the tab). The UI
        # reads this instantly on load and after every lazy refresh; the
        # value is only ever (re)written from a live BigQuery count, so it
        # trails the warehouse by at most one refresh and never drifts on
        # its own. A refreshed_at lets the reader decide when a value is too
        # stale to trust without a live re-count.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_listing_counts (
                business_id TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS zip_reference_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                status TEXT NOT NULL DEFAULT 'not_started',
                rows INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                started_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_repair_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                fixed INTEGER NOT NULL DEFAULT 0,
                manual_fixed INTEGER NOT NULL DEFAULT 0,
                processed INTEGER NOT NULL DEFAULT 0,
                remaining INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enrichment_queue (
                listing_id TEXT PRIMARY KEY,
                cycle_id INTEGER NOT NULL,
                queue_set TEXT NOT NULL CHECK (queue_set IN ('base', 'failed')),
                state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'processing', 'completed')),
                attempt_count INTEGER NOT NULL DEFAULT 0,
                claimed_at TIMESTAMP,
                completed_at TIMESTAMP,
                improved INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_enrichment_queue_cycle ON enrichment_queue (cycle_id, queue_set, state);")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mirror_quality_listings (
                listing_id TEXT PRIMARY KEY,
                event_id TEXT,
                business_id TEXT,
                brand TEXT,
                state TEXT,
                city TEXT,
                reasons TEXT,
                status TEXT,
                is_ai_enriched INTEGER NOT NULL DEFAULT 0,
                raw_record TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_mirror_brand ON mirror_quality_listings (brand);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_mirror_geo ON mirror_quality_listings (state, city);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_mirror_status ON mirror_quality_listings (status);")
        try:
            conn.execute("ALTER TABLE auto_repair_stats ADD COLUMN manual_fixed INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def seed_enrichment_cycle(listing_ids: list[str], cycle_id: int) -> int:
    """Replace the current pending base set with a new persisted cycle."""
    init_sqlite_cache()
    ids = sorted({str(value).strip() for value in listing_ids if str(value).strip()})
    with get_db_connection() as conn:
        conn.execute("DELETE FROM enrichment_queue")
        conn.executemany(
            "INSERT INTO enrichment_queue (listing_id, cycle_id, queue_set) VALUES (?, ?, 'base')",
            [(listing_id, int(cycle_id)) for listing_id in ids],
        )
        conn.commit()
    return len(ids)


def claim_enrichment_batch(cycle_id: int, limit: int = 2) -> list[str]:
    """Atomically claim a small batch from the active base set."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT listing_id FROM enrichment_queue WHERE cycle_id = ? AND queue_set = 'base' AND state = 'pending' ORDER BY listing_id LIMIT ?",
            (int(cycle_id), max(1, min(int(limit), 2))),
        ).fetchall()
        ids = [str(row["listing_id"]) for row in rows]
        if ids:
            now = datetime.now(timezone.utc).isoformat()
            conn.executemany(
                "UPDATE enrichment_queue SET state='processing', attempt_count=attempt_count+1, claimed_at=?, updated_at=CURRENT_TIMESTAMP WHERE listing_id=? AND cycle_id=? AND state='pending'",
                [(now, listing_id, int(cycle_id)) for listing_id in ids],
            )
            conn.commit()
        return ids


def complete_enrichment_claim(listing_id: str, cycle_id: int, improved: bool) -> None:
    """Complete a claim; unresolved rows enter the next cycle's failed set."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        if improved:
            conn.execute("UPDATE enrichment_queue SET state='completed', improved=1, completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE listing_id=? AND cycle_id=?", (listing_id, int(cycle_id)))
        else:
            conn.execute("UPDATE enrichment_queue SET state='completed', queue_set='failed', completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE listing_id=? AND cycle_id=?", (listing_id, int(cycle_id)))
        conn.commit()


def enrichment_cycle_counts(cycle_id: int) -> dict[str, int]:
    init_sqlite_cache()
    with get_db_connection() as conn:
        rows = conn.execute("SELECT queue_set, state, COUNT(*) AS count FROM enrichment_queue WHERE cycle_id=? GROUP BY queue_set, state", (int(cycle_id),)).fetchall()
    result = {"base_pending": 0, "base_processing": 0, "failed": 0, "completed": 0}
    for row in rows:
        if row["queue_set"] == "base" and row["state"] == "pending": result["base_pending"] = int(row["count"])
        if row["queue_set"] == "base" and row["state"] == "processing": result["base_processing"] = int(row["count"])
        if row["queue_set"] == "failed" and row["state"] == "completed": result["failed"] = int(row["count"])
        result["completed"] += int(row["count"])
    return result


def seed_or_swap_enrichment_cycle(incoming_listing_ids: list[str] | None = None) -> tuple[int, int]:
    """Seed or swap the enrichment queue cycle.
    If 'base' set has pending items, returns (current_cycle_id, pending_count).
    If 'base' set is exhausted:
      1. Collects all listing_ids currently in 'failed' set.
      2. Merges any newly incoming listing_ids.
      3. Increments cycle_id.
      4. Swaps them all into queue_set='base', state='pending', cycle_id=new_cycle_id.
    Returns (new_cycle_id, new_pending_count).
    """
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT MAX(cycle_id) AS max_cycle FROM enrichment_queue;").fetchone()
        has_prior = bool(row and row["max_cycle"] is not None)
        current_cycle = int(row["max_cycle"]) if has_prior else 0

        pending_row = conn.execute(
            "SELECT COUNT(*) AS count FROM enrichment_queue WHERE cycle_id = ? AND queue_set = 'base' AND state = 'pending';",
            (current_cycle,)
        ).fetchone() if has_prior else None
        pending_count = int(pending_row["count"] or 0) if pending_row else 0

        incoming_set = {str(lid).strip() for lid in (incoming_listing_ids or []) if str(lid).strip()}

        # If base is still actively working and has pending items:
        if pending_count > 0:
            if incoming_set:
                existing = {str(r["listing_id"]) for r in conn.execute("SELECT listing_id FROM enrichment_queue;").fetchall()}
                new_ids = incoming_set - existing
                if new_ids:
                    conn.executemany(
                        "INSERT OR IGNORE INTO enrichment_queue (listing_id, cycle_id, queue_set, state) VALUES (?, ?, 'base', 'pending');",
                        [(lid, current_cycle) for lid in new_ids]
                    )
                    conn.commit()
                updated_pending = conn.execute(
                    "SELECT COUNT(*) AS count FROM enrichment_queue WHERE cycle_id = ? AND queue_set = 'base' AND state = 'pending';",
                    (current_cycle,)
                ).fetchone()
                return current_cycle, int(updated_pending["count"] or 0) if updated_pending else 0
            return current_cycle, pending_count

        # If base has no pending items, swap failed set to become the new base set!
        failed_rows = conn.execute(
            "SELECT listing_id, attempt_count FROM enrichment_queue WHERE queue_set = 'failed';"
        ).fetchall()

        all_ids_to_run = set(incoming_set)
        attempt_counts = {}
        for r in failed_rows:
            lid = str(r["listing_id"])
            all_ids_to_run.add(lid)
            attempt_counts[lid] = int(r["attempt_count"] or 0)

        if not all_ids_to_run:
            return current_cycle, 0

        new_cycle = current_cycle + 1
        conn.execute("DELETE FROM enrichment_queue WHERE improved = 1;")
        conn.execute("DELETE FROM enrichment_queue WHERE queue_set = 'failed';")

        conn.executemany(
            """INSERT OR REPLACE INTO enrichment_queue 
               (listing_id, cycle_id, queue_set, state, attempt_count, updated_at)
               VALUES (?, ?, 'base', 'pending', ?, CURRENT_TIMESTAMP);""",
            [(lid, new_cycle, attempt_counts.get(lid, 0)) for lid in sorted(all_ids_to_run)]
        )
        conn.commit()
        return new_cycle, len(all_ids_to_run)


def replace_quality_mirror(rows: list[dict[str, Any]]) -> None:
    """Persist the latest invalid/review rows for fast quality reporting."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM mirror_quality_listings")
        conn.executemany("""
            INSERT OR REPLACE INTO mirror_quality_listings
            (listing_id, event_id, business_id, brand, state, city, reasons, status, is_ai_enriched, raw_record)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (str(row.get("listing_id") or f"{row.get('event_id','')}:{row.get('row_number','')}"), row.get("event_id"), row.get("business_id"), row.get("brand"), row.get("state"), row.get("city"), json.dumps(row.get("quality_reasons", [])), row.get("status", "needs_review"), int(bool(row.get("is_ai_enriched"))), json.dumps(row.get("raw_record"), default=str))
            for row in rows
        ])
        conn.commit()


def clear_sample_reporting_mirror(business_ids: list[str], brand_names: list[str]) -> None:
    """Remove known sample/demo brands from local reporting mirrors."""
    init_sqlite_cache()
    clean_business_ids = sorted({str(value).strip() for value in business_ids if str(value).strip()})
    clean_brand_names = sorted({str(value).strip() for value in brand_names if str(value).strip()})
    with get_db_connection() as conn:
        if clean_business_ids:
            placeholders = ",".join("?" for _ in clean_business_ids)
            conn.execute(f"DELETE FROM mirror_reporting_locations WHERE business_id IN ({placeholders})", clean_business_ids)
            conn.execute(f"DELETE FROM mirror_businesses WHERE business_id IN ({placeholders})", clean_business_ids)
            conn.execute(f"DELETE FROM mirror_quality_listings WHERE business_id IN ({placeholders})", clean_business_ids)
        if clean_brand_names:
            placeholders = ",".join("?" for _ in clean_brand_names)
            conn.execute(f"DELETE FROM mirror_zip_brand_activity WHERE brand_name IN ({placeholders})", clean_brand_names)
            conn.execute(f"DELETE FROM mirror_reporting_locations WHERE brand IN ({placeholders})", clean_brand_names)
            conn.execute(f"DELETE FROM mirror_quality_listings WHERE brand IN ({placeholders})", clean_brand_names)
        conn.execute("""
            INSERT OR REPLACE INTO mirror_meta (id, synced_at, zip_brand_rows, location_rows, business_rows)
            VALUES (
                1,
                CURRENT_TIMESTAMP,
                (SELECT COUNT(*) FROM mirror_zip_brand_activity),
                (SELECT COUNT(*) FROM mirror_reporting_locations),
                (SELECT COUNT(*) FROM mirror_businesses)
            )
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


def find_nearest_zip_in_cache(lat: float, lon: float) -> dict[str, Any] | None:
    """Find the nearest cached US ZIP code and city to the given coordinates (snapping ocean/offshore coords)."""
    from whitespace_tool.geo_enrichment import find_nearest_city_and_zip
    init_sqlite_cache()
    with get_db_connection() as conn:
        return find_nearest_city_and_zip(lat, lon, conn)


def find_nearest_worldwide_city_in_cache(lat: float, lon: float, country: str | None = None) -> dict[str, Any] | None:
    """Find the nearest cached worldwide city to the given coordinates from cachedb."""
    from whitespace_tool.geo_enrichment import find_nearest_worldwide_city
    init_sqlite_cache()
    with get_db_connection() as conn:
        return find_nearest_worldwide_city(lat, lon, conn, country=country)


def lookup_cached_city_state(city: str | None, state: str | None) -> dict[str, Any] | None:
    """Fuzzy lookup of primary ZIP and coordinates for a city and state from cache."""
    from whitespace_tool.geo_enrichment import lookup_zip_and_coords_by_city_state
    init_sqlite_cache()
    with get_db_connection() as conn:
        return lookup_zip_and_coords_by_city_state(city, state, conn)


def get_cached_zipcode_count() -> int:
    """Return the durable ZIP mirror size without loading its rows."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM us_zipcodes;").fetchone()
        return int(row["count"] or 0)


def cache_worldwide_cities(records: list[dict[str, Any]]) -> int:
    """Cache worldwide city records into SQLite for lightning-fast local matching."""
    if not records:
        return 0
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.executemany("""
            INSERT INTO worldwide_cities
            (country_code, country_name, state_name, state_code, district, city, town, zip_code, latitude, longitude)
            VALUES (:country_code, :country_name, :state_name, :state_code, :district, :city, :town, :zip_code, :latitude, :longitude)
        """, [
            {
                "country_code": str(r.get("country_code") or r.get("COUNTRY_CODE") or "").strip().upper() or None,
                "country_name": str(r.get("country_name") or r.get("COUNTRY") or "").strip() or None,
                "state_name": str(r.get("state_name") or r.get("STATE") or "").strip() or None,
                "state_code": str(r.get("state_code") or r.get("STATE_CODE") or "").strip().upper() or None,
                "district": str(r.get("district") or r.get("DISTRICT") or "").strip() or None,
                "city": str(r.get("city") or r.get("CITY") or "").strip() or None,
                "town": str(r.get("town") or r.get("TOWN") or "").strip() or None,
                "zip_code": str(r.get("zip_code") or r.get("ZIP_CODE") or "").strip() or None,
                "latitude": float(r["latitude"]) if r.get("latitude") is not None or r.get("LATITUDE") is not None else None,
                "longitude": float(r["longitude"]) if r.get("longitude") is not None or r.get("LONGITUDE") is not None else None,
            }
            for r in records
        ])
        conn.commit()
    return len(records)


def get_cached_worldwide_city_count() -> int:
    """Return the number of cached worldwide city records."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM worldwide_cities;").fetchone()
        return int(row["count"] or 0) if row else 0


def get_zip_reference_status() -> dict[str, Any]:
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT status, rows, message, started_at, updated_at FROM zip_reference_status WHERE id = 1").fetchone()
        if row:
            return dict(row)
    return {"status": "not_started", "rows": 0, "message": "", "started_at": "", "updated_at": ""}


def set_zip_reference_status(status: str, rows: int = 0, message: str = "") -> None:
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO zip_reference_status (id, status, rows, message, started_at, updated_at)
            VALUES (1, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
              status=excluded.status,
              rows=excluded.rows,
              message=excluded.message,
              started_at=CASE WHEN excluded.status='loading' THEN CURRENT_TIMESTAMP ELSE zip_reference_status.started_at END,
              updated_at=CURRENT_TIMESTAMP
            """,
            (str(status), int(rows or 0), str(message or "")),
        )
        conn.commit()


def get_auto_repair_stats() -> dict[str, Any]:
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT fixed, manual_fixed, processed, remaining, updated_at FROM auto_repair_stats WHERE id = 1;").fetchone()
        return dict(row) if row else {"fixed": 0, "manual_fixed": 0, "processed": 0, "remaining": 0, "updated_at": ""}


def set_auto_repair_stats(fixed: int, processed: int, remaining: int, manual_fixed: int | None = None) -> None:
    init_sqlite_cache()
    with get_db_connection() as conn:
        current = conn.execute("SELECT manual_fixed FROM auto_repair_stats WHERE id = 1").fetchone()
        manual = int(manual_fixed if manual_fixed is not None else (current[0] if current else 0))
        conn.execute("INSERT OR REPLACE INTO auto_repair_stats (id, fixed, manual_fixed, processed, remaining, updated_at) VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP);", (int(fixed), manual, int(processed), int(remaining)))
        conn.commit()


def increment_manual_fixed_count(amount: int = 1) -> None:
    stats = get_auto_repair_stats()
    set_auto_repair_stats(stats["fixed"], stats["processed"], stats["remaining"], stats.get("manual_fixed", 0) + int(amount))


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


def clear_local_cache_db(include_reference_zips: bool = False) -> None:
    """Clear all local cache tables so SQLite matches an empty/cleared warehouse state."""
    init_sqlite_cache()
    tables_to_clear = [
        "query_cache",
        "error_listing_counts",
        "mirror_quality_listings",
        "auto_repair_stats",
        "enrichment_queue",
        "mirror_zip_brand_activity",
        "mirror_reporting_locations",
        "mirror_businesses",
        "mirror_meta",
    ]
    if include_reference_zips:
        tables_to_clear.extend(["us_zipcodes", "zip_reference_status"])

    with get_db_connection() as conn:
        for table in tables_to_clear:
            try:
                conn.execute(f"DELETE FROM {table};")
            except Exception as exc:
                LOGGER.warning("clear_local_cache_table_failed table=%s error=%s", table, exc)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO error_listing_counts (business_id, count, refreshed_at) VALUES ('', 0, CURRENT_TIMESTAMP);"
            )
            conn.execute("""
                INSERT OR REPLACE INTO auto_repair_stats (id, fixed, manual_fixed, processed, remaining, updated_at)
                VALUES (1, 0, 0, 0, 0, CURRENT_TIMESTAMP);
            """)
            conn.execute("""
                INSERT OR REPLACE INTO mirror_meta (id, synced_at, zip_brand_rows, location_rows, business_rows)
                VALUES (1, CURRENT_TIMESTAMP, 0, 0, 0);
            """)
        except Exception as exc:
            LOGGER.warning("clear_local_cache_defaults_failed error=%s", exc)
        conn.commit()


def get_error_count(business_id: str = "") -> int | None:
    """Return the last-known Review Error Listings count for a business
    (empty string = the all-businesses total), or None if it has never been
    written. None means "no cached value yet", distinct from a real 0."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT count FROM error_listing_counts WHERE business_id = ? LIMIT 1;",
            (business_id or "",),
        ).fetchone()
    return int(row["count"]) if row is not None else None


def set_error_count(business_id: str, count: int) -> None:
    """Persist a freshly-computed error count. Only ever called with a value
    that just came from the warehouse, so SQLite stays a faithful (if
    slightly delayed) mirror rather than an independently-mutated counter."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO error_listing_counts (business_id, count, refreshed_at) VALUES (?, ?, CURRENT_TIMESTAMP);",
            (business_id or "", int(count)),
        )
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
                f"INSERT INTO mirror_businesses ({', '.join(MIRROR_BUSINESS_COLUMNS)}) "
                f"VALUES ({', '.join(':' + c for c in MIRROR_BUSINESS_COLUMNS)})",
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
        return [dict(row) for row in conn.execute("SELECT * FROM mirror_businesses ORDER BY name").fetchall()]
