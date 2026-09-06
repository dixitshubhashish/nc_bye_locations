"""Data sources, remote source loading, sheet listing, and API connectors.

Provides source previews, remote public source loading with Socrata limits,
Dominos store locator API integration, brand listing/creation, and US ZIP reference preparation.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from whitespace_tool.source_adapters import (
    api_get_source,
    csv_source,
    excel_source,
    json_source,
    python_connector_source,
    xml_source,
)
from whitespace_tool.sources.demographics import fetch_bigquery_demographics, resolve_bigquery_connection
from whitespace_tool.sources.dominos_overpass import fetch_for_zips as fetch_dominos_from_overpass
from whitespace_tool.sources.dominos_store_locator import fetch_for_zips
from whitespace_tool.persistence.sqlite_cache import get_cached_query, invalidate_cache, set_cached_query
from whitespace_tool.persistence.warehouse_bigquery import TABLE_SCHEMAS


def _ws():
    """Lazy import wrapper returning workflow_server module object."""
    import whitespace_tool.workflow_server as ws
    return ws


SUPPORTED_SOURCE_TYPES = {"csv", "excel", "json", "xml", "api_get_json", "python_editor"}
MINIMUM_US_ZIP_REFERENCE_ROWS = 30000
MAX_REMOTE_SOURCE_BYTES = int(os.environ.get("MAPPER_MAX_REMOTE_SOURCE_MB", "150")) * 1024 * 1024
REMOTE_SOURCE_TIMEOUT_SECONDS = int(os.environ.get("MAPPER_REMOTE_SOURCE_TIMEOUT_SECONDS", "60"))
MIN_REMOTE_SOURCE_ROW_LIMIT = 10000
REMOTE_SOURCE_ROW_LIMITS = (250000, 100000, 50000, 25000, MIN_REMOTE_SOURCE_ROW_LIMIT)


def preview_source(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate source data structure preview for mapper UI."""
    source_type = payload["source_type"]
    record_path = payload.get("record_path") or None
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type: {source_type}")
    if source_type == "api_get_json":
        return api_get_source.preview_url(
            payload["api_url"],
            record_path,
            payload.get("headers"),
            payload.get("query_params"),
            payload.get("auth"),
        )
    if source_type == "python_editor":
        content = base64.b64decode(payload["content_base64"])
        return python_connector_source.preview(content, record_path)

    file_name = payload.get("file_name", "")
    content = base64.b64decode(payload["content_base64"])
    if source_type == "csv":
        return csv_source.preview(content, record_path)
    if source_type == "json":
        return json_source.preview(content, record_path)
    if source_type == "xml":
        return xml_source.preview(content, record_path)
    if source_type == "excel":
        return excel_source.preview(content, record_path, file_name)
    raise ValueError(f"Unsupported source_type: {source_type}")


def source_sheets(payload: dict[str, Any]) -> dict[str, Any]:
    """List available sheet names in an Excel workbook."""
    content = base64.b64decode(payload["content_base64"])
    file_name = payload.get("file_name", "")
    return {"sheets": excel_source.list_sheets(content, file_name)}


def _remote_source_request(url: str) -> tuple[bytes, str]:
    """Execute HTTP GET request fetching remote bytes and extracting filename."""
    request = urllib.request.Request(url, headers={"User-Agent": "CompetitiveWhitespaceTool/1.0"})
    with urllib.request.urlopen(request, timeout=REMOTE_SOURCE_TIMEOUT_SECONDS) as response:
        return response.read(MAX_REMOTE_SOURCE_BYTES + 1), Path(urlsplit(url).path).name or "remote_source"


def _is_socrata_url(parsed_url: Any) -> bool:
    """Determine whether parsed URL points to a Socrata open data portal endpoint."""
    host = parsed_url.netloc.lower()
    path = parsed_url.path.lower()
    return (
        host.endswith("data.lacity.org")
        or host.endswith("socrata.com")
        or "/resource/" in path
        or path.endswith("/query.json")
    )


def _with_socrata_limit(url: str, row_limit: int) -> str:
    """Attach Socrata $limit query parameter to URL for payload size capping."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("$limit", str(row_limit))
    query.setdefault("limit", str(row_limit))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_public_source(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch remote public HTTP/HTTPS data file with safety size limits."""
    url = str(payload.get("url", "")).strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source URL must be a public HTTP or HTTPS URL")
    content, file_name = _remote_source_request(url)
    limited_url = ""
    limited_rows = 0
    if len(content) > MAX_REMOTE_SOURCE_BYTES and _is_socrata_url(parsed):
        for row_limit in REMOTE_SOURCE_ROW_LIMITS:
            candidate_url = _with_socrata_limit(url, row_limit)
            candidate_content, candidate_file_name = _remote_source_request(candidate_url)
            if len(candidate_content) <= MAX_REMOTE_SOURCE_BYTES:
                content = candidate_content
                file_name = candidate_file_name
                limited_url = candidate_url
                limited_rows = row_limit
                break
    if len(content) > MAX_REMOTE_SOURCE_BYTES:
        raise ValueError(
            f"Remote source exceeds the {MAX_REMOTE_SOURCE_BYTES // 1024 // 1024} MB loading limit. "
            f"Automatic limiting will not load fewer than {MIN_REMOTE_SOURCE_ROW_LIMIT} rows; "
            "use a source URL with a filter before loading it."
        )
    response = {"content_base64": base64.b64encode(content).decode("ascii"), "file_name": file_name}
    if limited_url:
        response.update({
            "limited": True,
            "limited_url": limited_url,
            "limited_rows": limited_rows,
            "warning": f"Remote source was larger than the app loading window, so the mapper loaded the first {limited_rows} rows from a limited source URL.",
        })
    return response


def _load_mapped_zip_demographics(zip_codes: set[str]) -> dict[str, Any]:
    """Load demographic attributes from BigQuery for a specific set of ZIP codes."""
    root_dir = Path(__file__).resolve().parent.parent.parent
    config_path = Path(os.environ.get("WORKFLOW_CONFIG", "config/demo.json"))
    if not config_path.is_absolute() and not config_path.exists():
        config_path = root_dir / config_path
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    source = config.get("demographics_source", {})
    if source.get("type") != "bigquery" or not zip_codes:
        return {}
    project_id, credentials_json = resolve_bigquery_connection(source, {"_config_dir": str(config_path.parent)})
    quoted_zips = ", ".join(f"'{zip_code}'" for zip_code in sorted(zip_codes))
    query = f"SELECT * FROM ({source['query'].rstrip(';')}) AS public_zips WHERE zip_code IN ({quoted_zips})"
    _ws().LOGGER.info("zip_lookup_started source=%s zip_count=%d", source.get("name", "public_demographics"), len(zip_codes))
    demographics = fetch_bigquery_demographics(
        project_id, query, source.get("name", "public_demographics"), credentials_json
    )
    _ws().LOGGER.info("zip_lookup_succeeded requested=%d matched=%d", len(zip_codes), len(demographics))
    return demographics


def prepare_zipcodes() -> dict[str, Any]:
    """Ensure US ZIP reference table is loaded into BigQuery bronze layer."""
    started_at = perf_counter()
    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    cache_key = (project_id, dataset_id)
    cached = _ws().ZIP_REFERENCE_CACHE.get(cache_key)
    if cached:
        _ws().LOGGER.info("zip_reference_timing phase=cache_hit elapsed_ms=%.1f", (perf_counter() - started_at) * 1000)
        return dict(cached)
    client = _ws()._bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.us_zipcodes"
    metadata_started_at = perf_counter()
    _ws()._ensure_dataset(client, project_id, dataset_id)
    try:
        existing = client.get_table(table_ref)
        row_count = existing.num_rows or 0
        _ws().LOGGER.info("zip_reference_timing phase=metadata_check elapsed_ms=%.1f rows=%d", (perf_counter() - metadata_started_at) * 1000, row_count)
        if row_count >= MINIMUM_US_ZIP_REFERENCE_ROWS:
            _ws().LOGGER.info("zip_reference_ready table=%s rows=%d", table_ref, row_count)
            result = {"status": "ready", "rows": int(row_count), "loaded": True, "created": False, "source": "bronze_copy", "table": table_ref}
            _ws().ZIP_REFERENCE_CACHE[cache_key] = result
            _ws().LOGGER.info("zip_reference_timing phase=ready_total elapsed_ms=%.1f", (perf_counter() - started_at) * 1000)
            return dict(result)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise

    root_dir = Path(__file__).resolve().parent.parent.parent
    config_path = Path(os.environ.get("WORKFLOW_CONFIG", "config/demo.json"))
    if not config_path.is_absolute() and not config_path.exists():
        config_path = root_dir / config_path
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    source = config.get("demographics_source", {})
    source_project_id, _source_credentials_json = resolve_bigquery_connection(source, {"_config_dir": str(config_path.parent)})
    if source_project_id != project_id:
        _ws().LOGGER.info("zip_reference_source_project source_project=%s target_project=%s", source_project_id, project_id)
    _ws().LOGGER.info("zip_reference_load_started table=%s", table_ref)
    copy_started_at = perf_counter()
    client.query(_zip_reference_copy_sql(table_ref, source["query"], source.get("name", "public_demographics"))).result()
    _ws().LOGGER.info("zip_reference_timing phase=bq_copy elapsed_ms=%.1f", (perf_counter() - copy_started_at) * 1000)
    copied = client.get_table(table_ref)
    row_count = int(copied.num_rows or 0)
    if row_count < MINIMUM_US_ZIP_REFERENCE_ROWS:
        raise RuntimeError(f"US ZIP reference copy returned only {row_count} rows")
    _ws().LOGGER.info("zip_reference_load_succeeded table=%s rows=%d", table_ref, row_count)
    result = {"status": "ready", "rows": row_count, "loaded": True, "created": True, "source": "bronze_copy", "table": table_ref}
    _ws().ZIP_REFERENCE_CACHE[cache_key] = result
    _ws().LOGGER.info("zip_reference_timing phase=rebuild_total elapsed_ms=%.1f", (perf_counter() - started_at) * 1000)
    return dict(result)


def _zip_reference_copy_sql(table_ref: str, source_query: str, source_name: str) -> str:
    """Build CREATE OR REPLACE TABLE query for copying us_zipcodes reference table."""
    query = source_query.rstrip(";")
    source_literal = json.dumps(source_name)
    hash_fields = """
        CAST(zip_code AS STRING) AS zip_code,
        CAST(city_name AS STRING) AS city_name,
        CAST(county AS STRING) AS county,
        CAST(state_code AS STRING) AS state_code,
        CAST(state_name AS STRING) AS state_name,
        CAST(latitude AS STRING) AS latitude,
        CAST(longitude AS STRING) AS longitude,
        CAST(population AS STRING) AS population,
        CAST(median_household_income AS STRING) AS median_household_income,
        CAST(median_age AS STRING) AS median_age,
        CAST(households AS STRING) AS households,
        CAST(income_per_capita AS STRING) AS income_per_capita,
        CAST(poverty AS STRING) AS poverty,
        CAST(employed_population AS STRING) AS employed_population,
        CAST(unemployed_population AS STRING) AS unemployed_population,
        CAST(housing_units AS STRING) AS housing_units,
        source AS source
    """
    return f"""
    CREATE OR REPLACE TABLE `{table_ref}`
    CLUSTER BY state_code, county, zip_code
    AS
    WITH source_zips AS (
      {query}
    ),
    normalized AS (
      SELECT
        LPAD(SUBSTR(CAST(zip_code AS STRING), 1, 5), 5, '0') AS zip_code,
        CAST(city AS STRING) AS city_name,
        CAST(county AS STRING) AS county,
        UPPER(TRIM(CAST(state_code AS STRING))) AS state_code,
        CAST(state_name AS STRING) AS state_name,
        SAFE_CAST(latitude AS FLOAT64) AS latitude,
        SAFE_CAST(longitude AS FLOAT64) AS longitude,
        SAFE_CAST(population AS FLOAT64) AS population,
        SAFE_CAST(median_household_income AS FLOAT64) AS median_household_income,
        SAFE_CAST(median_age AS FLOAT64) AS median_age,
        SAFE_CAST(households AS FLOAT64) AS households,
        SAFE_CAST(income_per_capita AS FLOAT64) AS income_per_capita,
        SAFE_CAST(poverty AS FLOAT64) AS poverty,
        SAFE_CAST(employed_population AS FLOAT64) AS employed_population,
        SAFE_CAST(unemployed_population AS FLOAT64) AS unemployed_population,
        SAFE_CAST(housing_units AS FLOAT64) AS housing_units,
        {source_literal} AS source
      FROM source_zips
      WHERE zip_code IS NOT NULL
    )
    SELECT
      *,
      TO_HEX(SHA256(TO_JSON_STRING(STRUCT({hash_fields})))) AS content_hash
    FROM normalized
    QUALIFY ROW_NUMBER() OVER (PARTITION BY zip_code ORDER BY population DESC NULLS LAST) = 1
    """


def _dominos_zip_codes(client: Any, project_id: str, dataset_id: str, limit: int | None) -> list[str]:
    """Query list of 5-digit ZIP codes from us_zipcodes reference table."""
    from google.cloud import bigquery

    table_ref = f"{project_id}.{dataset_id}.us_zipcodes"
    limit_sql = "LIMIT @limit" if limit else ""
    query = f"SELECT zip_code FROM `{table_ref}` WHERE zip_code IS NOT NULL ORDER BY zip_code {limit_sql}"
    params = []
    if limit:
        params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    return [str(row["zip_code"]).zfill(5)[:5] for row in client.query(query, job_config=job_config).result()]


def dominos_source(
    limit: int | None = 1,
    order_type: str = "Delivery",
    stores_per_zip: int | None = 1,
    max_workers: int = 8,
    one_per_zip: bool = False,
    provider: str = "auto",
) -> dict[str, Any]:
    """Fetch Domino's store locator locations across requested US ZIP codes."""
    prepare_zipcodes()
    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    safe_limit = max(1, min(int(limit or 0), 50000)) if limit else None
    safe_order_type = order_type if order_type in {"Delivery", "Carryout"} else "Delivery"
    zip_codes = _dominos_zip_codes(client, project_id, dataset_id, safe_limit)
    safe_stores_per_zip = max(1, min(int(stores_per_zip or 0), 1000)) if stores_per_zip else None
    safe_max_workers = max(1, min(int(max_workers or 1), 24))
    safe_provider = provider if provider in {"auto", "dominos", "osm"} else "auto"
    if safe_provider == "osm":
        result = fetch_dominos_from_overpass(zip_codes, one_per_zip=one_per_zip, max_workers=min(safe_max_workers, 8))
    else:
        result = fetch_for_zips(
            zip_codes,
            order_type=safe_order_type,
            stores_per_zip=1 if one_per_zip else safe_stores_per_zip,
            one_per_zip=one_per_zip,
            max_workers=safe_max_workers,
        )
        if safe_provider == "auto" and not result["Stores"] and result["errors"]:
            fallback = fetch_dominos_from_overpass(zip_codes, one_per_zip=one_per_zip, max_workers=min(safe_max_workers, 8))
            fallback["primary_errors"] = result["errors"]
            result = fallback

    if one_per_zip and result.get("Stores"):
        seen_zips: set[str] = set()
        one_per_zip_stores: list[dict[str, Any]] = []
        for store in result["Stores"]:
            zip_val = str(
                store.get("QueryZip")
                or store.get("PostalCode")
                or store.get("ZipCode")
                or store.get("Address", {}).get("PostalCode")
                or ""
            ).strip()[:5]
            if zip_val and zip_val in seen_zips:
                continue
            if zip_val:
                seen_zips.add(zip_val)
            one_per_zip_stores.append(store)
        result["Stores"] = one_per_zip_stores

    result["requested_zip_limit"] = safe_limit
    result["requested_stores_per_zip"] = 1 if one_per_zip else safe_stores_per_zip
    result["requested_max_workers"] = safe_max_workers
    result["requested_one_per_zip"] = one_per_zip
    result["requested_provider"] = safe_provider
    result["dedupe_key"] = "StoreID"
    return result


def list_brands(search: str = "") -> dict[str, Any]:
    """List registered brands matching search criteria."""
    cache_key = f"list_brands:{search.strip().lower()}"
    cached = get_cached_query(cache_key)
    if cached:
        return cached

    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    _ensure_source_types_table(client, project_id, dataset_id)
    _ensure_workflow_templates_table(client, project_id, dataset_id)
    query = f"""
    SELECT
      b.business_id,
      b.name,
      b.slug,
      b.website_url,
      b.status,
      COALESCE(b.source_type_id, t.source_type_id, JSON_VALUE(t.components, '$.source_type_id'), JSON_VALUE(t.components, '$.mapper.source_type_id')) AS source_type_id,
      st.name AS source_type_name
    FROM `{project_id}.{dataset_id}.businesses` b
    LEFT JOIN `{project_id}.{dataset_id}.workflow_templates` t
      ON b.business_id = t.business_id
    LEFT JOIN `{project_id}.{dataset_id}.source_types` st
      ON COALESCE(b.source_type_id, t.source_type_id, JSON_VALUE(t.components, '$.source_type_id'), JSON_VALUE(t.components, '$.mapper.source_type_id')) = st.source_type_id
    WHERE b.is_deleted IS NOT TRUE
      AND (@search = '' OR LOWER(b.name) LIKE CONCAT('%', LOWER(@search), '%'))
    QUALIFY ROW_NUMBER() OVER (PARTITION BY b.business_id ORDER BY t.updated_at DESC NULLS LAST) = 1
    ORDER BY b.name
    LIMIT 100
    """
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("search", "STRING", search)])
    res = {"brands": [dict(row) for row in client.query(query, job_config=config).result()]}
    set_cached_query(cache_key, res)
    return res


def _ensure_businesses_table(client: Any, project_id: str, dataset_id: str) -> None:
    """Ensure businesses table exists with required schema in dataset."""
    from google.cloud import bigquery

    table_ref = f"{project_id}.{dataset_id}.businesses"
    _ws()._ensure_dataset(client, project_id, dataset_id)
    try:
        existing = client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        schema = [
            bigquery.SchemaField(
                field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")
            )
            for field in TABLE_SCHEMAS["businesses"]
        ]
        client.create_table(bigquery.Table(table_ref, schema=schema))
        return
    existing_names = {field.name for field in existing.schema}
    missing_fields = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")
        )
        for field in TABLE_SCHEMAS["businesses"]
        if field["name"] not in existing_names
    ]
    if missing_fields:
        existing.schema = list(existing.schema) + missing_fields
        client.update_table(existing, ["schema"])


def _ensure_source_types_table(client: Any, project_id: str, dataset_id: str) -> None:
    """Ensure source_types table exists with required schema in dataset."""
    from google.cloud import bigquery

    _ws()._ensure_dataset(client, project_id, dataset_id)
    table_ref = f"{project_id}.{dataset_id}.source_types"
    schema = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")
        )
        for field in TABLE_SCHEMAS["source_types"]
    ]
    try:
        client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(bigquery.Table(table_ref, schema=schema))


def _ensure_workflow_templates_table(client: Any, project_id: str, dataset_id: str) -> None:
    """Ensure workflow_templates table exists with required schema in dataset."""
    from google.cloud import bigquery

    _ws()._ensure_dataset(client, project_id, dataset_id)
    table_ref = f"{project_id}.{dataset_id}.workflow_templates"
    schema = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")
        )
        for field in TABLE_SCHEMAS["workflow_templates"]
    ]
    try:
        existing = client.get_table(table_ref)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise
        client.create_table(bigquery.Table(table_ref, schema=schema))
        return
    existing_names = {field.name for field in existing.schema}
    missing_fields = [
        bigquery.SchemaField(
            field["name"], field["type"], mode=field["mode"], default_value_expression=field.get("default")
        )
        for field in TABLE_SCHEMAS["workflow_templates"]
        if field["name"] not in existing_names
    ]
    if missing_fields:
        existing.schema = list(existing.schema) + missing_fields
        client.update_table(existing, ["schema"])


def ensure_source_type(source_type: str) -> str:
    """Ensure source type exists in the database and return its ID."""
    try:
        from google.cloud import bigquery

        project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
        client = _ws()._bigquery_client(project_id, credentials_json)
        table_ref = f"{project_id}.{dataset_id}.source_types"
        _ensure_source_types_table(client, project_id, dataset_id)
        query = f"SELECT source_type_id FROM `{table_ref}` WHERE name = @name LIMIT 1"
        params = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("name", "STRING", source_type)])
        found = list(client.query(query, job_config=params).result())
        if found:
            return found[0]["source_type_id"]
        insert = f"INSERT INTO `{table_ref}` (name, data_format, created_at) VALUES (@name, @format, CURRENT_TIMESTAMP())"
        params = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("name", "STRING", source_type),
                bigquery.ScalarQueryParameter("format", "JSON", json.dumps({"type": source_type})),
            ]
        )
        client.query(insert, job_config=params).result()
        found = list(
            client.query(
                query, job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("name", "STRING", source_type)])
            ).result()
        )
        if not found:
            return f"source-{source_type}"
        return found[0]["source_type_id"]
    except Exception:
        return f"source-{source_type}"


def create_brand(data: dict[str, Any]) -> dict[str, Any]:
    """Create a new brand record in the businesses table."""
    from google.cloud import bigquery

    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Brand name is required")
    slug = str(data.get("slug") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
    source_type = str(data.get("source_type", "")).strip()
    raw_source_type_id = str(data.get("source_type_id", "")).strip()
    source_type_id = (
        ensure_source_type(source_type or raw_source_type_id)
        if raw_source_type_id in SUPPORTED_SOURCE_TYPES
        else raw_source_type_id
    )
    source_type_id = source_type_id or (ensure_source_type(source_type) if source_type else "")
    if not source_type_id:
        raise ValueError("Source type is required")
    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    _ensure_businesses_table(client, project_id, dataset_id)
    query = f"""
    INSERT INTO `{project_id}.{dataset_id}.businesses`
      (name, slug, source_type_id, description, logo_url, website_url, status, created_at, updated_at, meta_title, meta_description, country_of_origin)
    VALUES (@name, @slug, @source_type_id, @description, @logo_url, @website_url, @status, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), @meta_title, @meta_description, @country_of_origin)
    """
    params = [
        bigquery.ScalarQueryParameter("name", "STRING", name),
        bigquery.ScalarQueryParameter("slug", "STRING", slug),
        bigquery.ScalarQueryParameter("source_type_id", "STRING", source_type_id),
        bigquery.ScalarQueryParameter("description", "STRING", data.get("description")),
        bigquery.ScalarQueryParameter("logo_url", "STRING", data.get("logo_url")),
        bigquery.ScalarQueryParameter("website_url", "STRING", data.get("website_url")),
        bigquery.ScalarQueryParameter("status", "STRING", data.get("status") or "active"),
        bigquery.ScalarQueryParameter("meta_title", "STRING", data.get("meta_title")),
        bigquery.ScalarQueryParameter("meta_description", "STRING", data.get("meta_description")),
        bigquery.ScalarQueryParameter("country_of_origin", "STRING", data.get("country_of_origin")),
    ]
    client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    lookup = f"""
    SELECT b.business_id, b.name, b.slug, b.website_url, b.status, b.source_type_id, st.name AS source_type_name
    FROM `{project_id}.{dataset_id}.businesses` b
    LEFT JOIN `{project_id}.{dataset_id}.source_types` st
      ON b.source_type_id = st.source_type_id
    WHERE b.is_deleted IS NOT TRUE AND b.slug = @slug
    ORDER BY b.created_at DESC
    LIMIT 1
    """
    result = list(
        client.query(
            lookup, job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("slug", "STRING", slug)])
        ).result()
    )
    if not result:
        raise RuntimeError("Brand was created but its database-generated ID could not be read back")
    invalidate_cache()
    return {"brand": dict(result[0])}


def list_source_types() -> dict[str, Any]:
    """List available data source formats and connector types."""
    project_id, dataset_id, credentials_json = _ws()._warehouse_settings()
    client = _ws()._bigquery_client(project_id, credentials_json)
    _ensure_source_types_table(client, project_id, dataset_id)
    for source_type in ("csv", "json", "excel", "xml", "api_get_json", "python_editor"):
        ensure_source_type(source_type)
    try:
        rows = client.query(
            f"SELECT source_type_id, name FROM `{project_id}.{dataset_id}.source_types` ORDER BY name"
        ).result()
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"source_types": []}
        raise
    return {"source_types": [dict(row) for row in rows]}
