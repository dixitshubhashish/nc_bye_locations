"""Medallion Architecture ETL layer operations.

Manages silver enrichment layer creation, gold aggregated view definitions,
mirror caching, and background synchronization scheduling.
"""

from __future__ import annotations

import os
import threading
from time import sleep
from typing import Any

import whitespace_tool.workflow_server as ws
from whitespace_tool.persistence.sqlite_cache import invalidate_cache, replace_gold_mirror


def _proper_case_sql(column_expr: str) -> str:
    """Build SQL expression converting input column string to Title/Proper Case."""
    return f"REGEXP_REPLACE(INITCAP(TRIM({column_expr})), r\"'S\\b\", \"'s\")"


def build_silver_layer() -> dict[str, Any]:
    """Transform bronze raw listings into enriched silver layer tables."""
    project_id, bronze_dataset_id, silver_dataset_id, _gold_dataset_id, credentials_json = ws._medallion_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    ws._ensure_dataset(client, project_id, bronze_dataset_id)
    ws._ensure_dataset(client, project_id, silver_dataset_id)
    bronze_ref = f"{project_id}.{bronze_dataset_id}"
    silver_ref = f"{project_id}.{silver_dataset_id}"
    zip_reference_table = f"{silver_ref}.zip_reference"
    enriched_table = f"{silver_ref}.listings_enriched"
    invalid_table = f"{silver_ref}.listings_invalid"
    top_view = f"{silver_ref}.vw_brand_location_top10"
    brand_zip_view = f"{silver_ref}.vw_brand_zip_income"
    client.query(f"DROP TABLE IF EXISTS `{enriched_table}`").result()
    client.query(f"DROP TABLE IF EXISTS `{invalid_table}`").result()

    zip_city_case = _proper_case_sql("city_name")
    zip_county_case = _proper_case_sql("county")
    zip_state_name_case = _proper_case_sql("state_name")

    client.query(f"""
    CREATE OR REPLACE TABLE `{zip_reference_table}`
    CLUSTER BY state_code, zip_code
    AS
    SELECT
      zip_code,
      {zip_city_case} AS city_name,
      {zip_county_case} AS county,
      UPPER(TRIM(state_code)) AS state_code,
      {zip_state_name_case} AS state_name,
      latitude,
      longitude,
      population,
      median_household_income,
      median_age,
      income_per_capita,
      households,
      poverty,
      employed_population,
      unemployed_population,
      housing_units,
      source,
      CURRENT_TIMESTAMP() AS silver_updated_at
    FROM `{bronze_ref}.us_zipcodes`
    QUALIFY ROW_NUMBER() OVER (PARTITION BY zip_code ORDER BY population DESC NULLS LAST) = 1
    """).result()

    brand_name_case = _proper_case_sql("COALESCE(b.name, l.business_id)")
    location_name_case = _proper_case_sql("l.name")
    city_name_case = _proper_case_sql("COALESCE(z.city_name, NULLIF(TRIM(l.city_name), ''))")
    county_case = _proper_case_sql("z.county")
    state_name_case = _proper_case_sql("z.state_name")

    mandatory_check = """
      brand_name IS NOT NULL AND brand_name != ''
      AND name IS NOT NULL AND name != ''
      AND address IS NOT NULL AND address != ''
      AND city_name IS NOT NULL AND city_name != ''
      AND state_code IS NOT NULL AND state_code != ''
      AND zip_code IS NOT NULL AND zip_code != ''
      AND latitude IS NOT NULL AND longitude IS NOT NULL
    """
    rejection_reason_expr = """
      ARRAY_TO_STRING(ARRAY(
        SELECT reason FROM UNNEST([
          IF(brand_name IS NULL OR brand_name = '', 'missing_brand', NULL),
          IF(name IS NULL OR name = '', 'missing_name', NULL),
          IF(address IS NULL OR address = '', 'missing_address', NULL),
          IF(city_name IS NULL OR city_name = '', 'missing_city', NULL),
          IF(state_code IS NULL OR state_code = '', 'missing_state', NULL),
          IF(zip_code IS NULL OR zip_code = '', 'missing_zip', NULL),
          IF(latitude IS NULL OR longitude IS NULL, 'unresolved_coordinates', NULL)
        ]) AS reason
        WHERE reason IS NOT NULL
      ), ', ')
    """

    query = f"""
    CREATE OR REPLACE TABLE `{silver_ref}._listings_staging`
    PARTITION BY DATE(first_observed_at)
    CLUSTER BY state_code, zip_code, business_id
    AS
    WITH normalized_listings AS (
      SELECT
        *,
        COALESCE(first_observed_at, CURRENT_TIMESTAMP()) AS first_observed_at_coalesced,
        REGEXP_EXTRACT(CAST(zip_code AS STRING), r'(\\d{{5}})') AS normalized_zip_code,
        LOWER(TRIM(city_name)) AS normalized_city_name,
        UPPER(TRIM(state_code)) AS normalized_state_code
      FROM `{bronze_ref}.listings`
      WHERE is_deleted IS NOT TRUE
    ),
    unique_zips AS (
      SELECT * FROM `{zip_reference_table}`
    ),
    city_geos AS (
      SELECT
        LOWER(TRIM(city_name)) AS normalized_city_name,
        state_code AS normalized_state_code,
        AVG(latitude) AS latitude,
        AVG(longitude) AS longitude
      FROM unique_zips
      WHERE city_name IS NOT NULL
        AND state_code IS NOT NULL
        AND latitude IS NOT NULL
        AND longitude IS NOT NULL
      GROUP BY normalized_city_name, normalized_state_code
    )
    SELECT
      l.listing_id,
      l.business_id,
      {brand_name_case} AS brand_name,
      l.source_type_id,
      l.location_key,
      {location_name_case} AS name,
      l.address,
      {city_name_case} AS city_name,
      {county_case} AS county,
      COALESCE(z.state_code, NULLIF(UPPER(TRIM(l.state_code)), '')) AS state_code,
      {state_name_case} AS state_name,
      l.normalized_zip_code AS zip_code,
      'United States' AS country,
      COALESCE(l.latitude, z.latitude, cg.latitude) AS latitude,
      COALESCE(l.longitude, z.longitude, cg.longitude) AS longitude,
      CASE
        WHEN l.latitude IS NOT NULL AND l.longitude IS NOT NULL THEN 'source_listing'
        WHEN z.latitude IS NOT NULL AND z.longitude IS NOT NULL THEN 'zip_centroid'
        WHEN cg.latitude IS NOT NULL AND cg.longitude IS NOT NULL THEN 'city_state_centroid'
        ELSE 'unresolved'
      END AS coordinate_source,
      CASE
        WHEN l.latitude IS NOT NULL AND l.longitude IS NOT NULL THEN 1.0
        WHEN z.latitude IS NOT NULL AND z.longitude IS NOT NULL THEN 0.75
        WHEN cg.latitude IS NOT NULL AND cg.longitude IS NOT NULL THEN 0.55
        ELSE 0.0
      END AS coordinate_confidence,
      ARRAY_TO_STRING(
        ARRAY(
          SELECT part
          FROM UNNEST([
            NULLIF(TRIM(l.address), ''),
            NULLIF(TRIM(l.city_name), ''),
            NULLIF(TRIM(l.state_code), ''),
            l.normalized_zip_code
          ]) AS part
          WHERE part IS NOT NULL
        ),
        ', '
      ) AS geocode_query,
      l.phone_number,
      l.content_hash,
      l.first_observed_at_coalesced AS first_observed_at,
      l.last_observed_at,
      z.population,
      z.median_household_income,
      z.median_age,
      z.income_per_capita,
      COUNT(*) OVER (PARTITION BY l.normalized_zip_code, LOWER(TRIM(l.address))) AS similar_address_count,
      CURRENT_TIMESTAMP() AS silver_updated_at
    FROM normalized_listings l
    LEFT JOIN `{bronze_ref}.businesses` b
      ON l.business_id = b.business_id
      AND b.is_deleted IS NOT TRUE
    LEFT JOIN unique_zips z
      ON l.normalized_zip_code = z.zip_code
    LEFT JOIN city_geos cg
      ON COALESCE(l.normalized_city_name, LOWER(TRIM(z.city_name))) = cg.normalized_city_name
      AND COALESCE(l.normalized_state_code, UPPER(TRIM(z.state_code))) = cg.normalized_state_code
    WHERE l.is_deleted IS NOT TRUE
      AND (
        LOWER(COALESCE(l.country, 'us')) IN ('', 'us', 'u.s.', 'u.s.a.', 'usa', 'united states', 'united states of america')
      )
      AND (
        COALESCE(l.latitude, z.latitude, cg.latitude) IS NULL OR (
          COALESCE(l.latitude, z.latitude, cg.latitude) BETWEEN 13.0 AND 72.0 AND (
            (COALESCE(l.longitude, z.longitude, cg.longitude) BETWEEN -180.0 AND -64.0) OR (COALESCE(l.longitude, z.longitude, cg.longitude) BETWEEN 144.0 AND 146.0)
          )
        )
      )
    """
    client.query(query).result()

    staging_table = f"{silver_ref}._listings_staging"
    client.query(f"""
    CREATE OR REPLACE TABLE `{enriched_table}`
    PARTITION BY DATE(first_observed_at)
    CLUSTER BY state_code, zip_code, business_id
    AS
    SELECT * FROM `{staging_table}`
    WHERE {mandatory_check}
    """).result()
    client.query(f"""
    CREATE OR REPLACE TABLE `{invalid_table}`
    PARTITION BY DATE(first_observed_at)
    CLUSTER BY state_code, zip_code, business_id
    AS
    SELECT *, {rejection_reason_expr} AS rejection_reason
    FROM `{staging_table}`
    WHERE NOT ({mandatory_check})
    """).result()
    client.query(f"DROP TABLE IF EXISTS `{staging_table}`").result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{top_view}` AS
    SELECT
      brand_name,
      name,
      address,
      city_name,
      county,
      state_code,
      state_name,
      country,
      zip_code,
      latitude,
      longitude,
      coordinate_source,
      coordinate_confidence,
      median_household_income,
      population
    FROM `{enriched_table}`
    """).result()
    client.query(f"""
    CREATE OR REPLACE VIEW `{brand_zip_view}` AS
    SELECT
      brand_name,
      zip_code,
      city_name,
      county,
      state_code,
      state_name,
      country,
      COUNT(*) AS location_count,
      MAX(population) AS population,
      MAX(median_household_income) AS median_household_income,
      MAX(income_per_capita) AS income_per_capita
    FROM `{enriched_table}`
    GROUP BY brand_name, zip_code, city_name, county, state_code, state_name, country
    """).result()
    table = client.get_table(enriched_table)
    invalid_rows = client.get_table(invalid_table)
    invalidate_cache()
    return {
        "bronze_dataset": bronze_ref,
        "silver_dataset": silver_ref,
        "zip_reference_table": zip_reference_table,
        "enriched_table": enriched_table,
        "invalid_table": invalid_table,
        "views": [top_view, brand_zip_view],
        "rows": int(table.num_rows or 0),
        "invalid_rows": int(invalid_rows.num_rows or 0),
    }


def build_gold_layer() -> dict[str, Any]:
    """Define aggregated analytical views over silver enriched listings."""
    project_id, bronze_dataset_id, silver_dataset_id, gold_dataset_id, credentials_json = ws._medallion_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    ws._ensure_dataset(client, project_id, gold_dataset_id)
    bronze_ref = f"{project_id}.{bronze_dataset_id}"
    silver_ref = f"{project_id}.{silver_dataset_id}"
    gold_ref = f"{project_id}.{gold_dataset_id}"
    enriched_table = f"{silver_ref}.listings_enriched"

    zip_brand_view = f"{gold_ref}.vw_zip_brand_activity"
    brand_view = f"{gold_ref}.vw_brand_summary"
    location_view = f"{gold_ref}.vw_reporting_locations"
    filters_view = f"{gold_ref}.vw_reporting_filter_options"
    gap_base_view = f"{gold_ref}.vw_reporting_gap_base"

    for dead_view in (
        "vw_state_summary",
        "vw_city_summary",
        "vw_listing_quality_summary",
        "vw_geo_reference",
        "vw_reporting_totals",
        "vw_reporting_state_brand",
        "vw_reporting_city_brand",
        "vw_reporting_zip_summary",
    ):
        client.query(f"DROP VIEW IF EXISTS `{gold_ref}.{dead_view}`").result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{zip_brand_view}` AS
    SELECT
      z.zip_code,
      z.state_code,
      z.state_name,
      z.county,
      z.city_name,
      z.population,
      z.median_household_income,
      z.median_age,
      z.latitude,
      z.longitude,
      l.brand_name,
      COUNT(l.listing_id) AS location_count,
      MAX(l.last_observed_at) AS last_observed_at
    FROM `{silver_ref}.zip_reference` z
    LEFT JOIN `{enriched_table}` l ON z.zip_code = l.zip_code
    GROUP BY z.zip_code, z.state_code, z.state_name, z.county, z.city_name,
      z.population, z.median_household_income, z.median_age, z.latitude, z.longitude, l.brand_name
    """).result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{brand_view}` AS
    SELECT
      brand_name,
      SUM(location_count) AS location_count,
      COUNT(DISTINCT state_code) AS state_count,
      COUNT(DISTINCT county) AS county_count,
      COUNT(DISTINCT city_name) AS city_count,
      COUNT(DISTINCT zip_code) AS zip_count
    FROM `{zip_brand_view}`
    WHERE brand_name IS NOT NULL AND location_count > 0
    GROUP BY brand_name
    """).result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{location_view}` AS
    SELECT
      l.listing_id,
      l.business_id,
      l.brand_name AS brand,
      l.name,
      l.address,
      l.city_name,
      l.state_code,
      l.state_name,
      l.county,
      l.zip_code,
      l.phone_number,
      l.latitude,
      l.longitude,
      l.coordinate_source,
      l.coordinate_confidence,
      l.country,
      l.last_observed_at,
      z.population,
      z.median_household_income,
      z.median_age
    FROM `{enriched_table}` l
    LEFT JOIN `{silver_ref}.zip_reference` z ON l.zip_code = z.zip_code
    WHERE l.listing_id IS NOT NULL
    """).result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{filters_view}` AS
    SELECT 'brand' AS filter_type, brand_name AS filter_value, brand_name AS filter_label,
      CAST(NULL AS STRING) AS state_code, CAST(NULL AS STRING) AS county, CAST(NULL AS STRING) AS city_name, CAST(NULL AS STRING) AS zip_code
    FROM `{brand_view}`
    UNION DISTINCT
    SELECT 'brand', name, name, CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING)
    FROM `{bronze_ref}.businesses`
    WHERE is_deleted IS NOT TRUE AND COALESCE(status, 'active') = 'active'
    UNION ALL
    SELECT DISTINCT 'state', state_code, COALESCE(state_name, state_code), state_code, CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING)
    FROM `{zip_brand_view}` WHERE state_code IS NOT NULL
    UNION ALL
    SELECT DISTINCT 'county', county, CONCAT(county, ', ', state_code), state_code, county, CAST(NULL AS STRING), CAST(NULL AS STRING)
    FROM `{zip_brand_view}` WHERE county IS NOT NULL AND state_code IS NOT NULL
    UNION ALL
    SELECT DISTINCT 'city', city_name, CONCAT(city_name, ', ', state_code), state_code, county, city_name, CAST(NULL AS STRING)
    FROM `{zip_brand_view}` WHERE city_name IS NOT NULL AND state_code IS NOT NULL
    UNION ALL
    SELECT DISTINCT 'zip', zip_code, CONCAT(zip_code, ' (', city_name, ', ', state_code, ')'), state_code, county, city_name, zip_code
    FROM `{zip_brand_view}` WHERE zip_code IS NOT NULL
    """).result()

    client.query(f"""
    CREATE OR REPLACE VIEW `{gap_base_view}` AS
    SELECT
      zip_code,
      state_code,
      state_name,
      county,
      city_name,
      population,
      median_household_income,
      median_age,
      latitude,
      longitude,
      brand_name,
      location_count
    FROM `{zip_brand_view}`
    """).result()

    return {
        "gold_dataset": gold_ref,
        "views": [zip_brand_view, brand_view, location_view, filters_view, gap_base_view],
    }


def sync_gold_mirror() -> dict[str, Any]:
    """Pull gold layer view datasets into SQLite local cache mirror."""
    project_id, _bronze, _silver, gold_dataset_id, credentials_json = ws._medallion_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    gold_ref = f"{project_id}.{gold_dataset_id}"

    zip_brand_query = f"""
    SELECT zip_code, state_code, state_name, county, city_name,
           population, median_household_income, median_age,
           latitude, longitude, brand_name, location_count
    FROM `{gold_ref}.vw_zip_brand_activity`
    """
    zip_rows = [dict(row) for row in client.query(zip_brand_query).result()]

    loc_query = f"""
    SELECT listing_id, business_id, brand, name, address, city_name,
           state_code, state_name, county, zip_code, phone_number,
           latitude, longitude, coordinate_source, coordinate_confidence,
           country, population, median_household_income, median_age
    FROM `{gold_ref}.vw_reporting_locations`
    """
    loc_rows = [dict(row) for row in client.query(loc_query).result()]

    biz_query = f"""
    SELECT business_id, name, slug, status, source_type_id
    FROM `{project_id}.{_bronze}.businesses`
    WHERE is_deleted IS NOT TRUE
    ORDER BY name
    """
    biz_rows = [dict(row) for row in client.query(biz_query).result()]

    replace_gold_mirror(zip_rows, loc_rows, biz_rows)
    return {"mirrored_zip_rows": len(zip_rows), "mirrored_loc_rows": len(loc_rows), "mirrored_biz_rows": len(biz_rows)}


def _rebuild_gold_and_mirror() -> dict[str, Any]:
    """Rebuild gold analytical layer views and refresh local SQLite mirror."""
    gold_result = ws.build_gold_layer()
    mirror_result = ws.sync_gold_mirror()
    return {"gold": gold_result, "mirror": mirror_result}


def _refresh_silver_background() -> bool:
    """Asynchronously execute silver+gold rebuild in background thread."""
    with ws.REPORTING_REFRESH_LOCK:
        if ws.REPORTING_REFRESHING:
            return False
        ws.REPORTING_REFRESHING = True

    def worker():
        try:
            ws.LOGGER.info("background_medallion_refresh_started")
            ws.build_silver_layer()
            ws._rebuild_gold_and_mirror()
            ws.LOGGER.info("background_medallion_refresh_succeeded")
        except Exception as exc:
            ws.LOGGER.exception("background_medallion_refresh_failed error=%s", exc)
        finally:
            with ws.REPORTING_REFRESH_LOCK:
                ws.REPORTING_REFRESHING = False

    t = threading.Thread(target=worker, daemon=True, name="reporting-silver-refresh")
    t.start()
    return True


def _start_silver_gold_scheduler() -> None:
    """Start background daemon thread periodically checking for periodic rebuilds."""
    interval_hours = int(os.environ.get("MEDALLION_REFRESH_HOURS", "1"))
    if interval_hours <= 0:
        return

    def scheduler_loop():
        ws.LOGGER.info("medallion_scheduler_started interval_hours=%d", interval_hours)
        while True:
            sleep(interval_hours * 3600)
            try:
                ws.LOGGER.info("scheduled_medallion_refresh_triggered")
                _refresh_silver_background()
            except Exception as exc:
                ws.LOGGER.exception("scheduled_medallion_refresh_error error=%s", exc)

    t = threading.Thread(target=scheduler_loop, daemon=True, name="silver-gold-scheduler")
    t.start()
