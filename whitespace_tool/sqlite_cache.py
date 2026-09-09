from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import functools
import json
import logging
import sqlite3
import time
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
    # Source columns no typed field covers, carried bronze -> silver -> gold
    # -> mirror so custom fields survive every read path, not just the
    # warehouse. Stored as the JSON text gold hands over.
    "custom_fields",
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
        # Same top-up migration mirror_businesses already had: an existing
        # cache file predates any column added later, and replace_gold_mirror()
        # INSERTs every MIRROR_LOCATION_COLUMNS name explicitly, so without
        # this the first sync after an upgrade fails with "no such column".
        existing_location_columns = {row["name"] for row in conn.execute("PRAGMA table_info(mirror_reporting_locations)").fetchall()}
        for column in MIRROR_LOCATION_COLUMNS:
            if column not in existing_location_columns:
                column_type = "REAL" if column in {"latitude", "longitude", "coordinate_confidence", "population", "median_household_income", "median_age"} else "TEXT"
                conn.execute(f"ALTER TABLE mirror_reporting_locations ADD COLUMN {column} {column_type};")
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
        # Records every cachedb action whose wall-clock time crossed
        # SLOW_ACTION_THRESHOLD_MS, so a slow SQLite path (contention, a
        # missing index, WAL checkpoint stalls) is visible and queryable
        # instead of only showing up as vague overall slowness. Trimmed to
        # the most recent MAX_SLOW_ACTION_ROWS on every insert - this table
        # itself must not become the memory/growth problem it's meant to
        # catch on a 512MB deployment.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cachedb_action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                detail TEXT,
                occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cachedb_action_log_occurred ON cachedb_action_log (occurred_at);")
        # Job History: one row per save_mapper() call (fresh source save or
        # a single-record reprocess), so the UI can show recent jobs with
        # their status without the user having to infer it from a
        # transient "Starting batch..." progress message that disappears
        # once the save finishes. Local/ephemeral like auto_repair_stats -
        # not BigQuery-authoritative, purely a UI convenience.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS save_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                brand TEXT,
                total_rows INTEGER NOT NULL DEFAULT 0,
                mapped_rows INTEGER NOT NULL DEFAULT 0,
                error_listings INTEGER NOT NULL DEFAULT 0,
                duplicate_listings_skipped INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_save_events_created ON save_events (created_at);")
        # Tracks, per source_type, whenever the fixed discovery-sample field
        # count (parse only inspects the first N records) turned out to
        # miss fields that the full save later found - the raw signal a
        # future adaptive discovery-sample size would learn from. Purely
        # observational for now: it does not change today's discovery
        # sample size, which is a documented product contract, not
        # something to silently vary based on this data.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS field_discovery_learning (
                source_type_id TEXT PRIMARY KEY,
                sample_field_count INTEGER NOT NULL,
                full_field_count INTEGER NOT NULL,
                missed_fields TEXT,
                observed_count INTEGER NOT NULL DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Advancing confidence score per (target field, source column name)
        # pairing - kept-as-suggested (+1), switched to a different mapped
        # field (+0.5), switched to unmapped (-0.5), or a brand-new manual
        # pairing with no prior suggestion (+1) all accumulate here, so a
        # field's auto-mapping suggestion gets more (or less) confident the
        # more it's actually used/kept across real saves - "advanced AI
        # kinda mapping" that stabilizes with usage instead of a fixed hint
        # list. source_field_normalized collapses casing/punctuation
        # differences (e.g. "Cuisine Type" and "cuisine_type" both learn
        # into the same row) so the same real-world column name accrues
        # one score regardless of how a given source spells it.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS field_mapping_confidence (
                target_key TEXT NOT NULL,
                source_field_normalized TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                sample_count INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (target_key, source_field_normalized)
            );
        """)
        # Small durable key/value store for user-configurable settings that
        # need to survive a page reload and be shared by every reader (e.g.
        # the "how many days without an update counts as stale" threshold
        # behind the Stale Records metric) - deliberately not in
        # query_cache, which is a throwaway derived-payload cache.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        try:
            conn.execute("ALTER TABLE auto_repair_stats ADD COLUMN manual_fixed INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()


SLOW_ACTION_THRESHOLD_MS = 200.0
MAX_SLOW_ACTION_ROWS = 500


def _record_slow_action(action: str, duration_ms: float, detail: str = "") -> None:
    """Best-effort: never let logging a slow action itself become a second
    failure. Not wrapped by _timed_cache_action, so it isn't measured/logged
    against its own threshold."""
    LOGGER.warning("cachedb_slow_action action=%s duration_ms=%.1f detail=%s", action, duration_ms, detail)
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO cachedb_action_log (action, duration_ms, detail) VALUES (?, ?, ?)",
                (action, duration_ms, detail),
            )
            conn.execute(
                "DELETE FROM cachedb_action_log WHERE id NOT IN "
                "(SELECT id FROM cachedb_action_log ORDER BY id DESC LIMIT ?)",
                (MAX_SLOW_ACTION_ROWS,),
            )
            conn.commit()
    except Exception:
        LOGGER.debug("cachedb_slow_action_log_write_failed action=%s", action, exc_info=True)


def _timed_cache_action(func):
    """Wrap a cachedb function so every call is timed; calls at or above
    SLOW_ACTION_THRESHOLD_MS are logged and persisted via
    _record_slow_action(), so a slow cachedb path is queryable later
    (get_slow_actions()) instead of only ever showing up as vague overall
    slowness."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            if duration_ms >= SLOW_ACTION_THRESHOLD_MS:
                _record_slow_action(func.__name__, duration_ms)
    return wrapper


def get_slow_actions(limit: int = 50) -> list[dict[str, Any]]:
    """Most recent cachedb actions that crossed SLOW_ACTION_THRESHOLD_MS,
    newest first - for a future admin/debug view or ad-hoc inspection."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT action, duration_ms, detail, occurred_at FROM cachedb_action_log "
            "ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), MAX_SLOW_ACTION_ROWS)),),
        ).fetchall()
        return [dict(row) for row in rows]


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
    """Atomically claim a small batch from the active base set.

    Claimed in random order, not by listing_id: ids from one brand tend to
    sort together, so ordered claiming spent the early (and most likely to be
    seen) part of every cycle on a single brand. Randomising spreads coverage
    across brands - the full base set still drains either way, since each row
    leaves 'pending' as soon as it is claimed.
    """
    init_sqlite_cache()
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT listing_id FROM enrichment_queue WHERE cycle_id = ? AND queue_set = 'base' AND state = 'pending' ORDER BY RANDOM() LIMIT ?",
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
                "zip_code": str(r.get("zip_code", "")).strip().upper(),
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


def cache_missing_zipcodes(zip_records: list[dict[str, Any]]) -> int:
    if not zip_records:
        return 0
    init_sqlite_cache()
    with get_db_connection() as conn:
        before = conn.total_changes
        conn.executemany("""
            INSERT OR IGNORE INTO us_zipcodes (
                zip_code, city_name, county, state_code, state_name,
                latitude, longitude, population, median_household_income, median_age
            ) VALUES (
                :zip_code, :city_name, :county, :state_code, :state_name,
                :latitude, :longitude, :population, :median_household_income, :median_age
            );
        """, [
            {
                "zip_code": str(r.get("zip_code", "")).strip().upper(),
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
        return conn.total_changes - before


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
                "zip_code": str(r.get("zip_code") or r.get("ZIP_CODE") or "").strip().upper() or None,
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
            # reporting_quality:* entries are exempt from this blanket wipe.
            # Unlike every other cached payload here, reporting_quality_summary()
            # already re-warms itself in the background on every single read
            # of a warm entry (see its own should_refresh/_QUALITY_REFRESH_KEYS
            # logic) - it doesn't need invalidation to eventually reflect a
            # new save/reprocess. Wiping it anyway forced the Data Quality
            # tab back into a genuinely-cold ~30-40s BigQuery recompute after
            # *any* save/reprocess anywhere in the app, unlike Location
            # Intelligence's tab, which reads dedicated gold-mirror tables
            # untouched by this delete. Exempting it keeps quality numbers
            # fast (self-healing within a read or two) the same way.
            conn.execute("DELETE FROM query_cache WHERE cache_key NOT LIKE 'reporting_quality:%';")
        conn.commit()


def invalidate_quality_cache() -> None:
    """Explicitly drop the reporting_quality:* payloads that invalidate_cache()
    deliberately spares. Needed when something the quality numbers are
    *computed from* changes (e.g. the stale-after-days threshold), as opposed
    to the underlying listings changing - which the summary already re-warms
    itself for on every read."""
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_cache WHERE cache_key LIKE 'reporting_quality:%';")
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
        clauses.append("UPPER(zip_code) = ?")
        params.append(zip_code.upper())
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


MAX_SAVE_EVENT_ROWS = 200


def record_save_event(
    event_id: str, brand: str, total_rows: int, mapped_rows: int,
    error_listings: int, duplicate_listings_skipped: int,
) -> None:
    """One row per save_mapper() call (a fresh source save or a single-
    record reprocess) - status is derived once here so every reader (the
    Job History panel) agrees on what OK/FAILED/NEEDS_REVIEW means."""
    if mapped_rows <= 0 and total_rows > 0:
        status = "FAILED"
    elif error_listings > 0:
        status = "NEEDS_REVIEW"
    else:
        status = "OK"
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO save_events (event_id, brand, total_rows, mapped_rows, error_listings, duplicate_listings_skipped, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, brand, total_rows, mapped_rows, error_listings, duplicate_listings_skipped, status),
        )
        conn.execute(
            "DELETE FROM save_events WHERE id NOT IN (SELECT id FROM save_events ORDER BY id DESC LIMIT ?)",
            (MAX_SAVE_EVENT_ROWS,),
        )
        conn.commit()


def record_field_discovery_gap(source_type_id: str, sample_field_count: int, full_field_count: int, missed_fields: list[str]) -> None:
    """Called from save_mapper() when the full source contained fields the
    fixed-size discovery sample never saw. Keeps the largest gap observed
    per source_type_id rather than every occurrence, since the useful
    signal is "how much bigger would the sample have needed to be", not a
    growing log."""
    if not source_type_id:
        return
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT full_field_count, observed_count FROM field_discovery_learning WHERE source_type_id = ?",
            (source_type_id,),
        ).fetchone()
        if existing and existing["full_field_count"] >= full_field_count:
            conn.execute(
                "UPDATE field_discovery_learning SET observed_count = observed_count + 1, updated_at = CURRENT_TIMESTAMP WHERE source_type_id = ?",
                (source_type_id,),
            )
        else:
            conn.execute(
                "INSERT INTO field_discovery_learning (source_type_id, sample_field_count, full_field_count, missed_fields, observed_count) "
                "VALUES (?, ?, ?, ?, 1) "
                "ON CONFLICT(source_type_id) DO UPDATE SET sample_field_count=excluded.sample_field_count, "
                "full_field_count=excluded.full_field_count, missed_fields=excluded.missed_fields, "
                "observed_count=field_discovery_learning.observed_count + 1, updated_at=CURRENT_TIMESTAMP",
                (source_type_id, sample_field_count, full_field_count, json.dumps(sorted(missed_fields))),
            )
        conn.commit()


def get_field_discovery_gaps(limit: int = 50) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT source_type_id, sample_field_count, full_field_count, missed_fields, observed_count, updated_at "
            "FROM field_discovery_learning ORDER BY (full_field_count - sample_field_count) DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [dict(row) for row in rows]


def _normalize_field_name(value: str) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def record_mapping_confidence_events(events: list[dict[str, Any]]) -> None:
    """events: [{"target_key": ..., "source_field": ..., "delta": float}, ...].
    Upserts each (target_key, normalized source_field) pair, accumulating
    score and sample_count rather than overwriting - the whole point is a
    running total across every save, not a single-save snapshot."""
    if not events:
        return
    with get_db_connection() as conn:
        for event in events:
            target_key = str(event.get("target_key") or "").strip()
            source_field = _normalize_field_name(event.get("source_field"))
            delta = event.get("delta")
            if not target_key or not source_field or not isinstance(delta, (int, float)):
                continue
            conn.execute(
                "INSERT INTO field_mapping_confidence (target_key, source_field_normalized, score, sample_count) "
                "VALUES (?, ?, ?, 1) "
                "ON CONFLICT(target_key, source_field_normalized) DO UPDATE SET "
                "score = score + excluded.score, sample_count = sample_count + 1, updated_at = CURRENT_TIMESTAMP",
                (target_key, source_field, float(delta)),
            )
        conn.commit()


def get_mapping_confidence(target_key: str = "") -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        if target_key:
            rows = conn.execute(
                "SELECT target_key, source_field_normalized, score, sample_count, updated_at "
                "FROM field_mapping_confidence WHERE target_key = ? ORDER BY score DESC",
                (target_key,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT target_key, source_field_normalized, score, sample_count, updated_at "
                "FROM field_mapping_confidence ORDER BY target_key, score DESC"
            ).fetchall()
        return [dict(row) for row in rows]


def get_recent_save_events(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT event_id, brand, total_rows, mapped_rows, error_listings, duplicate_listings_skipped, status, created_at "
            "FROM save_events ORDER BY id DESC LIMIT ? OFFSET ?",
            (max(1, min(int(limit), MAX_SAVE_EVENT_ROWS)), max(0, int(offset))),
        ).fetchall()
        return [dict(row) for row in rows]


DEFAULT_STALE_AFTER_DAYS = 90


def get_app_setting(key: str, default: str = "") -> str:
    init_sqlite_cache()
    with get_db_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ? LIMIT 1;", (key,)).fetchone()
        return str(row["value"]) if row else default


def set_app_setting(key: str, value: str) -> None:
    init_sqlite_cache()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;",
            (key, str(value)),
        )
        conn.commit()


def get_stale_after_days() -> int:
    """Days without an update before a listing counts as stale. User
    configurable (persisted), defaulting to the previously-hardcoded 90."""
    try:
        value = int(get_app_setting("stale_after_days", str(DEFAULT_STALE_AFTER_DAYS)))
    except (TypeError, ValueError):
        return DEFAULT_STALE_AFTER_DAYS
    return value if 1 <= value <= 3650 else DEFAULT_STALE_AFTER_DAYS


def count_save_events() -> int:
    with get_db_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM save_events").fetchone()
        return int(row["count"]) if row else 0


# Time every cachedb action below and persist the slow ones (see
# _timed_cache_action / cachedb_action_log). Wrapped in bulk here, after all
# definitions, rather than decorating each `def` individually, so this list
# is the single place that has to stay in sync with the module's public
# surface - get_db_connection (a @contextmanager, timing it would only
# measure generator setup, not the work done inside the `with` block),
# init_sqlite_cache (one-time schema setup, not a repeated action), and the
# logging helpers themselves are intentionally excluded.
for _action_name in (
    "seed_enrichment_cycle", "claim_enrichment_batch", "complete_enrichment_claim",
    "enrichment_cycle_counts", "seed_or_swap_enrichment_cycle", "replace_quality_mirror",
    "clear_sample_reporting_mirror", "cache_zipcodes", "cache_missing_zipcodes",
    "get_cached_zipcode", "find_nearest_zip_in_cache", "find_nearest_worldwide_city_in_cache",
    "lookup_cached_city_state", "get_cached_zipcode_count", "cache_worldwide_cities",
    "get_cached_worldwide_city_count", "get_zip_reference_status", "set_zip_reference_status",
    "get_auto_repair_stats", "set_auto_repair_stats", "increment_manual_fixed_count",
    "get_cached_query", "set_cached_query", "invalidate_cache", "clear_local_cache_db",
    "get_error_count", "set_error_count", "replace_gold_mirror", "get_mirror_status",
    "fetch_mirror_zip_brand_activity", "fetch_mirror_reporting_locations",
    "fetch_mirror_reporting_locations_by_brand", "fetch_mirror_businesses",
    "record_save_event", "get_recent_save_events", "count_save_events",
    "get_app_setting", "set_app_setting", "get_stale_after_days", "invalidate_quality_cache",
    "record_field_discovery_gap", "get_field_discovery_gaps",
    "record_mapping_confidence_events", "get_mapping_confidence",
):
    globals()[_action_name] = _timed_cache_action(globals()[_action_name])
del _action_name
