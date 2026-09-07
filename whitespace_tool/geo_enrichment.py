from __future__ import annotations

import math
import re
import sqlite3
from typing import Any

# Standard US 50 States + DC + Territories mapping
US_STATE_MAP: dict[str, str] = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KS": "KS", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC",
    "PUERTO RICO": "PR", "GUAM": "GU", "VIRGIN ISLANDS": "VI",
    "NORTHERN MARIANA ISLANDS": "MP", "AMERICAN SAMOA": "AS"
}

# Reverse mapping: code to upper name
US_CODE_MAP = {v: k for k, v in US_STATE_MAP.items()}


def normalize_state_code(state: str | None) -> str:
    """Normalize any state representation (full name, code, mixed case) to a 2-digit uppercase code."""
    if not state:
        return ""
    cleaned = re.sub(r"[^a-zA-Z\s]", "", str(state)).strip().upper()
    if cleaned in US_CODE_MAP:
        return cleaned
    if cleaned in US_STATE_MAP:
        return US_STATE_MAP[cleaned]
    two_letter = cleaned[:2]
    if two_letter in US_CODE_MAP:
        return two_letter
    return ""


def normalize_city_text(city: str | None) -> str:
    """Strip punctuation, common extraneous prefix/suffixes, and standardize abbreviations."""
    if not city:
        return ""
    text = str(city).lower().strip()
    # Remove prefix patterns like "city of", "town of", "village of", "borough of"
    text = re.sub(r"^(city|town|village|borough|municipality|twp|township)\s+(of\s+)?", "", text)
    replacements = [
        (r"\bn\.?y\.?c\.?\b", "new york "),
        (r"\bl\.?a\.?\b", "los angeles "),
        (r"\bst\.\s*", "saint "),
        (r"\bst\s+", "saint "),
        (r"\bft\.\s*", "fort "),
        (r"\bft\s+", "fort "),
        (r"\bmt\.\s*", "mount "),
        (r"\bmt\s+", "mount "),
        (r"\bn\.\s+(?=[a-z])", "north "),
        (r"\bs\.\s+(?=[a-z])", "south "),
        (r"\be\.\s+(?=[a-z])", "east "),
        (r"\bw\.\s+(?=[a-z])", "west "),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_and_fix_inverted_coords(lat: float | None, lon: float | None) -> tuple[float | None, float | None, bool]:
    """Detect if lat and lon are inverted (i.e. lat is longitude and lon is latitude in US).
    Returns (corrected_lat, corrected_lon, was_inverted).
    """
    if lat is None or lon is None:
        return lat, lon, False

    is_normal_lat = 13.0 <= lat <= 72.0
    is_normal_lon = (-180.0 <= lon <= -64.0) or (144.0 <= lon <= 146.0)

    is_inverted_lat = (-180.0 <= lat <= -64.0) or (144.0 <= lat <= 146.0)
    is_inverted_lon = 13.0 <= lon <= 72.0

    if not (is_normal_lat and is_normal_lon) and (is_inverted_lat and is_inverted_lon):
        return lon, lat, True

    return lat, lon, False


def is_us_land_coordinate(lat: float | None, lon: float | None) -> bool:
    """Return True if lat, lon falls within valid US bounds and is not Null Island (0,0)."""
    if lat is None or lon is None:
        return False
    if abs(lat) < 0.001 and abs(lon) < 0.001:
        return False
    in_us_lat = 13.0 <= lat <= 72.0
    in_us_lon = (-180.0 <= lon <= -64.0) or (144.0 <= lon <= 146.0)
    return in_us_lat and in_us_lon


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth in kilometers."""
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius * c


def find_nearest_city_and_zip(lat: float, lon: float, conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Find the nearest US city and ZIP code from us_zipcodes for any coordinates (including ocean/offshore)."""
    if lat is None or lon is None:
        return None

    delta = 2.0
    rows = conn.execute("""
        SELECT zip_code, city_name, county, state_code, state_name, latitude, longitude, population
        FROM us_zipcodes
        WHERE latitude BETWEEN ? AND ?
          AND longitude BETWEEN ? AND ?
          AND latitude IS NOT NULL AND longitude IS NOT NULL
    """, (lat - delta, lat + delta, lon - delta, lon + delta)).fetchall()

    if not rows:
        delta = 8.0
        rows = conn.execute("""
            SELECT zip_code, city_name, county, state_code, state_name, latitude, longitude, population
            FROM us_zipcodes
            WHERE latitude BETWEEN ? AND ?
              AND longitude BETWEEN ? AND ?
              AND latitude IS NOT NULL AND longitude IS NOT NULL
        """, (lat - delta, lat + delta, lon - delta, lon + delta)).fetchall()

    if not rows:
        rows = conn.execute("""
            SELECT zip_code, city_name, county, state_code, state_name, latitude, longitude, population
            FROM us_zipcodes
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY population DESC
            LIMIT 500
        """).fetchall()

    if not rows:
        return None

    best_match = None
    min_dist = float("inf")
    for r in rows:
        dist = haversine_distance_km(lat, lon, float(r["latitude"]), float(r["longitude"]))
        if dist < min_dist:
            min_dist = dist
            best_match = r

    if best_match:
        res = dict(best_match)
        res["distance_km"] = round(min_dist, 2)
        return res
    return None


def lookup_zip_and_coords_by_city_state(city: str | None, state: str | None, conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Find the primary ZIP code and coordinates for a city + state using realistic fuzzy matching."""
    norm_state = normalize_state_code(state)
    norm_city = normalize_city_text(city)
    if not norm_city:
        return None

    query_state = norm_state if norm_state else None

    if query_state:
        rows = conn.execute("""
            SELECT zip_code, city_name, county, state_code, state_name, latitude, longitude, population
            FROM us_zipcodes
            WHERE state_code = ?
            ORDER BY population DESC
        """, (query_state,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT zip_code, city_name, county, state_code, state_name, latitude, longitude, population
            FROM us_zipcodes
            ORDER BY population DESC
            LIMIT 2000
        """).fetchall()

    if not rows:
        return None

    # 1. Exact match on normalized city
    for r in rows:
        candidate = normalize_city_text(r["city_name"])
        if candidate and candidate == norm_city:
            return dict(r)

    # 2. Prefix / containment match
    for r in rows:
        candidate = normalize_city_text(r["city_name"])
        if candidate and len(candidate) >= 3 and (candidate.startswith(norm_city) or norm_city.startswith(candidate)):
            return dict(r)

    # 3. Word token overlap
    city_tokens = set(norm_city.split())
    best_overlap = None
    max_overlap_count = 0
    for r in rows:
        candidate = normalize_city_text(r["city_name"])
        if not candidate:
            continue
        cand_tokens = set(candidate.split())
        overlap = len(city_tokens & cand_tokens)
        if overlap > max_overlap_count:
            max_overlap_count = overlap
            best_overlap = r

    if best_overlap and max_overlap_count >= 1:
        return dict(best_overlap)

    return None


def find_nearest_worldwide_city(
    lat: float,
    lon: float,
    conn: sqlite3.Connection,
    country: str | None = None,
) -> dict[str, Any] | None:
    """Find the nearest worldwide city from worldwide_cities in cachedb for any coordinates (including ocean/offshore)."""
    if lat is None or lon is None:
        return None

    clean_country = str(country or "").strip().lower()
    has_country = bool(clean_country and clean_country not in ("worldwide", "global", "all"))

    for delta in (2.0, 6.0, 15.0, 45.0, 180.0):
        query = """
            SELECT country_code, country_name, state_name, state_code, district, city, town, zip_code, latitude, longitude
            FROM worldwide_cities
            WHERE latitude BETWEEN ? AND ?
              AND longitude BETWEEN ? AND ?
              AND latitude IS NOT NULL AND longitude IS NOT NULL
        """
        params: list[Any] = [lat - delta, lat + delta, lon - delta, lon + delta]
        if has_country:
            query += " AND (LOWER(country_code) = ? OR LOWER(country_name) LIKE ?)"
            params.extend([clean_country[:2], f"%{clean_country}%"])
        query += " LIMIT 500"

        try:
            rows = conn.execute(query, params).fetchall()
            if rows:
                break
        except sqlite3.OperationalError:
            return None
    else:
        # Fallback without country filter if no match within country
        if has_country:
            return find_nearest_worldwide_city(lat, lon, conn, country=None)
        return None

    best_match = None
    min_dist = float("inf")
    for r in rows:
        dist = haversine_distance_km(lat, lon, float(r["latitude"]), float(r["longitude"]))
        if dist < min_dist:
            min_dist = dist
            best_match = r

    if best_match:
        res = dict(best_match)
        res["distance_km"] = round(min_dist, 2)
        return res
    return None


def lookup_worldwide_city(
    town: str | None = None,
    city: str | None = None,
    district: str | None = None,
    state: str | None = None,
    country: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Lookup worldwide location by town, city, district, state, country hierarchy.
    Checks local SQLite worldwide_cities cache first; if missing, can query BigQuery sample_locations.worldwide_cities.
    """
    clean_town = normalize_city_text(town)
    clean_city = normalize_city_text(city)
    clean_district = normalize_city_text(district)
    clean_state = normalize_city_text(state)
    clean_country = (country or "").strip().lower()

    if not (clean_town or clean_city or clean_district or clean_state):
        return None

    # 1. Check local SQLite worldwide_cities cache in cachedb first
    if conn is not None:
        try:
            for candidate in (clean_town, clean_city, clean_district, clean_state):
                if not candidate:
                    continue
                # 1a. Exact match on city, town, or district
                query = """
                    SELECT country_code, country_name, state_name, state_code, district, city, town, zip_code, latitude, longitude
                    FROM worldwide_cities
                    WHERE (LOWER(city) = ? OR LOWER(town) = ? OR LOWER(district) = ?)
                """
                params: list[Any] = [candidate, candidate, candidate]
                if clean_country and clean_country not in ("us", "usa", "united states"):
                    query += " AND (LOWER(country_code) = ? OR LOWER(country_name) LIKE ?)"
                    params.extend([clean_country[:2], f"%{clean_country}%"])
                query += " LIMIT 1"
                row = conn.execute(query, params).fetchone()
                if row:
                    return dict(row)

                # 1b. Prefix match in cachedb
                query_prefix = """
                    SELECT country_code, country_name, state_name, state_code, district, city, town, zip_code, latitude, longitude
                    FROM worldwide_cities
                    WHERE (LOWER(city) LIKE ? OR LOWER(town) LIKE ?)
                """
                params_prefix: list[Any] = [f"{candidate}%", f"{candidate}%"]
                if clean_country and clean_country not in ("us", "usa", "united states"):
                    query_prefix += " AND (LOWER(country_code) = ? OR LOWER(country_name) LIKE ?)"
                    params_prefix.extend([clean_country[:2], f"%{clean_country}%"])
                query_prefix += " LIMIT 1"
                row_prefix = conn.execute(query_prefix, params_prefix).fetchone()
                if row_prefix:
                    return dict(row_prefix)
        except sqlite3.OperationalError:
            pass

    # 2. Query BigQuery sample_locations.worldwide_cities as authoritative source
    try:
        from whitespace_tool.workflow_server import _bigquery_client, _warehouse_settings
        project_id, dataset_id, credentials_json = _warehouse_settings()
        client = _bigquery_client(project_id, credentials_json)

        primary_target = clean_town or clean_city or clean_district or clean_state
        where_clauses = ["(LOWER(CITY) = @target OR LOWER(TOWN) = @target OR LOWER(DISTRICT) = @target)"]
        from google.cloud import bigquery
        params = [bigquery.ScalarQueryParameter("target", "STRING", primary_target)]

        if clean_country and clean_country not in ("us", "usa", "united states"):
            where_clauses.append("(LOWER(COUNTRY_CODE) = @cc OR LOWER(COUNTRY) LIKE @cname)")
            params.append(bigquery.ScalarQueryParameter("cc", "STRING", clean_country[:2]))
            params.append(bigquery.ScalarQueryParameter("cname", "STRING", f"%{clean_country}%"))

        bq_query = f"""
            SELECT COUNTRY_CODE AS country_code, COUNTRY AS country_name, STATE AS state_name,
                   STATE_CODE AS state_code, DISTRICT AS district, CITY AS city, TOWN AS town,
                   ZIP_CODE AS zip_code, LATITUDE AS latitude, LONGITUDE AS longitude
            FROM `{project_id}.sample_locations.worldwide_cities`
            WHERE {" AND ".join(where_clauses)}
            LIMIT 1
        """
        job = client.query(bq_query, job_config=bigquery.QueryJobConfig(query_parameters=params))
        rows = list(job.result())
        if rows:
            res = dict(rows[0])
            # Cache into SQLite for instant future lookup
            if conn is not None:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO worldwide_cities
                        (country_code, country_name, state_name, state_code, district, city, town, zip_code, latitude, longitude)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        res.get("country_code"), res.get("country_name"), res.get("state_name"),
                        res.get("state_code"), res.get("district"), res.get("city"),
                        res.get("town"), res.get("zip_code"), res.get("latitude"), res.get("longitude")
                    ))
                    conn.commit()
                except Exception:
                    pass
            return res
    except Exception:
        pass

    return None


def resolve_location_hierarchy(
    town: str | None = None,
    city: str | None = None,
    district: str | None = None,
    state: str | None = None,
    country: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Traverse location hierarchy: town > city > district > state > country.
    Checks US zipcodes cache first if US; falls back to worldwide cities for international or non-US data.
    """
    clean_country = str(country or "").strip().lower()
    is_us = clean_country in ("", "us", "usa", "united states", "united states of america", "u.s.", "u.s.a.")

    # 1. US Hierarchy traversal via us_zipcodes
    if is_us and conn is not None:
        # 1a. Town
        if town:
            res = lookup_zip_and_coords_by_city_state(town, state, conn)
            if res:
                return {
                    "latitude": res.get("latitude"),
                    "longitude": res.get("longitude"),
                    "city": res.get("city_name") or town,
                    "town": town,
                    "state": res.get("state_code") or state,
                    "state_code": res.get("state_code") or state,
                    "zip_code": res.get("zip_code"),
                    "country": "United States",
                    "matched_level": "town"
                }
        # 1b. City
        if city:
            res = lookup_zip_and_coords_by_city_state(city, state, conn)
            if res:
                return {
                    "latitude": res.get("latitude"),
                    "longitude": res.get("longitude"),
                    "city": res.get("city_name") or city,
                    "town": town or city,
                    "state": res.get("state_code") or state,
                    "state_code": res.get("state_code") or state,
                    "zip_code": res.get("zip_code"),
                    "country": "United States",
                    "matched_level": "city"
                }
        # 1c. District / County
        if district:
            res = lookup_zip_and_coords_by_city_state(district, state, conn)
            if res:
                return {
                    "latitude": res.get("latitude"),
                    "longitude": res.get("longitude"),
                    "city": res.get("city_name") or district,
                    "town": town or district,
                    "state": res.get("state_code") or state,
                    "state_code": res.get("state_code") or state,
                    "zip_code": res.get("zip_code"),
                    "country": "United States",
                    "matched_level": "district"
                }
        # 1d. State alone
        norm_state = normalize_state_code(state)
        if norm_state:
            state_row = conn.execute("""
                SELECT zip_code, city_name, state_code, state_name, latitude, longitude
                FROM us_zipcodes
                WHERE state_code = ?
                ORDER BY population DESC
                LIMIT 1
            """, (norm_state,)).fetchone()
            if state_row:
                return {
                    "latitude": state_row["latitude"],
                    "longitude": state_row["longitude"],
                    "city": state_row["city_name"],
                    "town": state_row["city_name"],
                    "state": state_row["state_code"],
                    "state_code": state_row["state_code"],
                    "zip_code": state_row["zip_code"],
                    "country": "United States",
                    "matched_level": "state"
                }

    # 2. International / Worldwide Hierarchy traversal
    ww = lookup_worldwide_city(town=town, city=city, district=district, state=state, country=country, conn=conn)
    if ww:
        return {
            "latitude": ww.get("latitude"),
            "longitude": ww.get("longitude"),
            "city": ww.get("city") or city or town,
            "town": ww.get("town") or town or city,
            "district": ww.get("district") or district,
            "state": ww.get("state_code") or ww.get("state_name") or state,
            "state_code": ww.get("state_code") or state,
            "zip_code": ww.get("zip_code"),
            "country": ww.get("country_name") or country or "Worldwide",
            "matched_level": "worldwide_city"
        }

    return None


def enrich_raw_listing_row(row: dict[str, Any], conn: sqlite3.Connection) -> dict[str, Any]:
    """Take a raw listing record and enrich missing/invalid location data:
    - Inverted lat/long are swapped; IF making it a US coordinate, sets city, town, state as well
    - Ocean/offshore/invalid coordinates are snapped to nearest city or resolved from hierarchy
    - Missing coordinates are resolved via town > city > district > state > country hierarchy
    - Missing ZIP code is inferred from hierarchy
    - State is normalized to 2-digit code
    """
    enriched = dict(row)

    raw_town = str(enriched.get("town") or "").strip()
    raw_city = str(enriched.get("city") or enriched.get("city_name") or "").strip()
    raw_district = str(enriched.get("district") or enriched.get("county") or "").strip()
    raw_state = str(enriched.get("state") or enriched.get("state_code") or enriched.get("province") or "").strip()
    raw_country = str(enriched.get("country") or "").strip()
    raw_zip = str(enriched.get("postal_code") or enriched.get("zip") or enriched.get("zip_code") or "").strip()

    raw_lat = None
    raw_lon = None
    for lat_key in ("latitude", "lat"):
        if enriched.get(lat_key) is not None:
            try:
                raw_lat = float(enriched[lat_key])
                break
            except (ValueError, TypeError):
                pass

    for lon_key in ("longitude", "lon", "lng"):
        if enriched.get(lon_key) is not None:
            try:
                raw_lon = float(enriched[lon_key])
                break
            except (ValueError, TypeError):
                pass

    # 1. Inversion check
    if raw_lat is not None and raw_lon is not None:
        fixed_lat, fixed_lon, was_inverted = detect_and_fix_inverted_coords(raw_lat, raw_lon)
        if was_inverted:
            raw_lat, raw_lon = fixed_lat, fixed_lon
            enriched["latitude"] = fixed_lat
            enriched["longitude"] = fixed_lon
            enriched["__coordinate_fix"] = "inversion_corrected"
            # User requirement: "lat swaping if making it of US then set city town state as well in the data"
            if is_us_land_coordinate(fixed_lat, fixed_lon):
                nearest_us = find_nearest_city_and_zip(fixed_lat, fixed_lon, conn)
                if nearest_us:
                    city_candidate = re.sub(r"\s+(city|town|cdp|village)$", "", str(nearest_us.get("city_name") or ""), flags=re.I).strip()
                    if city_candidate:
                        enriched["city"] = city_candidate
                        enriched["town"] = city_candidate
                        raw_city = city_candidate
                        raw_town = city_candidate
                    if nearest_us.get("state_code"):
                        enriched["state"] = nearest_us["state_code"]
                        enriched["state_code"] = nearest_us["state_code"]
                        raw_state = nearest_us["state_code"]
                    if nearest_us.get("zip_code"):
                        zip_str = str(nearest_us["zip_code"])
                        enriched["postal_code"] = zip_str
                        if "zip" in enriched: enriched["zip"] = zip_str
                        if "zip_code" in enriched: enriched["zip_code"] = zip_str
                        raw_zip = zip_str
            else:
                nearest_ww = find_nearest_worldwide_city(fixed_lat, fixed_lon, conn, country=raw_country)
                if nearest_ww:
                    if nearest_ww.get("city"):
                        enriched["city"] = nearest_ww["city"]
                        enriched["town"] = nearest_ww.get("town") or nearest_ww["city"]
                        raw_city = nearest_ww["city"]
                    if nearest_ww.get("state_code") or nearest_ww.get("state_name"):
                        st = nearest_ww.get("state_code") or nearest_ww.get("state_name")
                        enriched["state"] = st
                        enriched["state_code"] = st
                        raw_state = st
                    if nearest_ww.get("zip_code"):
                        zip_str = str(nearest_ww["zip_code"])
                        enriched["postal_code"] = zip_str
                        if "zip" in enriched: enriched["zip"] = zip_str
                        if "zip_code" in enriched: enriched["zip_code"] = zip_str
                        raw_zip = zip_str
                    if nearest_ww.get("country_name"):
                        enriched["country"] = nearest_ww["country_name"]

    # 2. State normalization
    norm_state = normalize_state_code(raw_state)
    if norm_state:
        enriched["state"] = norm_state
        if "state_code" in enriched:
            enriched["state_code"] = norm_state

    # 3. Clean ZIP extraction
    zip5 = ""
    zip_match = re.search(r"(\d{5})", raw_zip)
    if zip_match:
        zip5 = zip_match.group(1)

    # 4. Resolve coordinates if missing, outside US, or in ocean
    coords_valid = is_us_land_coordinate(raw_lat, raw_lon)

    if not coords_valid:
        # 4a. Try resolving from ZIP first
        if zip5:
            zip_row = conn.execute("SELECT * FROM us_zipcodes WHERE zip_code = ? LIMIT 1", (zip5,)).fetchone()
            if zip_row and zip_row["latitude"] is not None and zip_row["longitude"] is not None:
                enriched["latitude"] = float(zip_row["latitude"])
                enriched["longitude"] = float(zip_row["longitude"])
                if not raw_city and zip_row["city_name"]:
                    enriched["city"] = zip_row["city_name"]
                if not raw_town and zip_row["city_name"]:
                    enriched["town"] = zip_row["city_name"]
                if not norm_state and zip_row["state_code"]:
                    enriched["state"] = zip_row["state_code"]
                    norm_state = zip_row["state_code"]
                enriched["__coordinate_fix"] = "zip_centroid_snapped"
                coords_valid = True

        # 4b. Try resolving via hierarchy: town > city > district > state > country
        if not coords_valid and (raw_town or raw_city or raw_district or norm_state or raw_country):
            hier = resolve_location_hierarchy(
                town=raw_town, city=raw_city, district=raw_district, state=norm_state, country=raw_country, conn=conn
            )
            if hier and hier.get("latitude") is not None and hier.get("longitude") is not None:
                enriched["latitude"] = float(hier["latitude"])
                enriched["longitude"] = float(hier["longitude"])
                if not raw_city and hier.get("city"):
                    enriched["city"] = hier["city"]
                if not raw_town and hier.get("town"):
                    enriched["town"] = hier["town"]
                if not norm_state and hier.get("state_code"):
                    enriched["state"] = hier["state_code"]
                    norm_state = hier["state_code"]
                if not zip5 and hier.get("zip_code"):
                    zip5 = str(hier["zip_code"])
                    enriched["postal_code"] = zip5
                    if "zip" in enriched: enriched["zip"] = zip5
                    if "zip_code" in enriched: enriched["zip_code"] = zip5
                enriched["__coordinate_fix"] = f"{hier.get('matched_level', 'hierarchy')}_centroid_snapped"
                coords_valid = True

        # 4c. If raw coords exist in ocean/offshore and no text match, snap to nearest city
        if not coords_valid and raw_lat is not None and raw_lon is not None:
            clean_c = (raw_country or "").strip().lower()
            is_us_target = clean_c in ("", "us", "usa", "united states", "united states of america", "u.s.", "u.s.a.")
            if is_us_target:
                nearest = find_nearest_city_and_zip(raw_lat, raw_lon, conn)
            else:
                nearest = find_nearest_worldwide_city(raw_lat, raw_lon, conn, country=raw_country) or find_nearest_city_and_zip(raw_lat, raw_lon, conn)

            if nearest and nearest.get("latitude") is not None:
                enriched["latitude"] = float(nearest["latitude"])
                enriched["longitude"] = float(nearest["longitude"])
                matched_city = nearest.get("city_name") or nearest.get("city")
                if not raw_city and matched_city:
                    clean_c_name = re.sub(r"\s+(city|town|cdp|village)$", "", str(matched_city), flags=re.I).strip()
                    enriched["city"] = clean_c_name
                    if not raw_town: enriched["town"] = clean_c_name
                matched_state = nearest.get("state_code") or nearest.get("state_name")
                if not norm_state and matched_state:
                    enriched["state"] = matched_state
                    enriched["state_code"] = matched_state
                matched_zip = nearest.get("zip_code")
                if not zip5 and matched_zip:
                    zip5 = str(matched_zip)
                    enriched["postal_code"] = zip5
                    if "zip" in enriched: enriched["zip"] = zip5
                    if "zip_code" in enriched: enriched["zip_code"] = zip5
                matched_country = nearest.get("country_name")
                if matched_country and not raw_country:
                    enriched["country"] = matched_country
                enriched["__coordinate_fix"] = "nearest_city_snapped"
                coords_valid = True

    # 5. Missing ZIP code inference from hierarchy if still empty
    if not zip5 and (raw_town or raw_city) and (norm_state or raw_country):
        hier = resolve_location_hierarchy(
            town=raw_town, city=raw_city, district=raw_district, state=norm_state, country=raw_country, conn=conn
        )
        if hier and hier.get("zip_code"):
            zip5 = str(hier["zip_code"])
            enriched["postal_code"] = zip5
            if "zip" in enriched: enriched["zip"] = zip5
            if "zip_code" in enriched: enriched["zip_code"] = zip5
            if not coords_valid and hier.get("latitude") is not None:
                enriched["latitude"] = float(hier["latitude"])
                enriched["longitude"] = float(hier["longitude"])
                enriched["__coordinate_fix"] = "hierarchy_zip_inferred"

    return enriched
