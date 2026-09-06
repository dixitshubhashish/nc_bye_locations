"""Review error listing services.

Contains logic for fetching error listings, error counts, and reprocessing rejected records.
"""
from __future__ import annotations

import json
from typing import Any

from whitespace_tool.persistence.sqlite_cache import fetch_mirror_businesses
import whitespace_tool.workflow_server as ws


def _safe_json_dumps(value: Any) -> str:
    """Safely serialize value to JSON string, falling back to string representation."""
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return json.dumps(str(value))



def _get_bigquery_module():
    import sys
    if "google.cloud.bigquery" in sys.modules:
        return sys.modules["google.cloud.bigquery"]
    try:
        from google.cloud import bigquery
        return bigquery
    except ImportError:
        return getattr(sys.modules.get("google.cloud"), "bigquery", None)


def list_rejected(event_id: str = "") -> dict[str, Any]:
    """Retrieve error listings records for a batch or across all events."""
    bigquery = _get_bigquery_module()

    project_id, dataset_id, credentials_json = ws._warehouse_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    query = f"SELECT event_id, business_id, source_type_id, row_number, errors, raw_record FROM `{project_id}.{dataset_id}.error_listings` WHERE is_deleted IS NOT TRUE AND (@event_id = '' OR event_id = @event_id) ORDER BY event_id, row_number LIMIT 500"
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("event_id", "STRING", event_id)])
    try:
        result_rows = client.query(query, job_config=config).result()
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"records": []}
        raise
    records = []
    for row in result_rows:
        item = dict(row)
        for key in ("errors", "raw_record"):
            if isinstance(item.get(key), str):
                try:
                    item[key] = json.loads(item[key])
                except ValueError:
                    pass
        records.append(item)
    return {"records": records}


def _count_error_listings_live(business_id: str = "") -> int:
    """Query live BigQuery table for exact count of active error listings."""
    bigquery = _get_bigquery_module()

    project_id, dataset_id, credentials_json = ws._warehouse_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    query = f"SELECT COUNT(*) AS total FROM `{project_id}.{dataset_id}.error_listings` WHERE is_deleted IS NOT TRUE AND (@business_id = '' OR business_id = @business_id)"
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("business_id", "STRING", business_id)]
    )
    try:
        return int(next(iter(client.query(query, job_config=config).result()))["total"])
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return 0
        raise


def count_error_listings(business_id: str = "", refresh: bool = False) -> int:
    """Return total active error listings count for a business or overall, using SQLite cache."""
    from whitespace_tool.persistence.sqlite_cache import get_error_count, set_error_count

    if not refresh:
        cached = get_error_count(business_id)
        if cached is not None:
            return cached
    live_func = getattr(ws, "_count_error_listings_live", _count_error_listings_live)
    live = live_func(business_id)
    set_error_count(business_id, live)
    return live


def refresh_error_count(business_id: str = "") -> int:
    """Force re-count from live BigQuery and update local SQLite error count cache."""
    return count_error_listings(business_id, refresh=True)


def reprocess_rejected(data: dict[str, Any]) -> dict[str, Any]:
    """Reprocess rejected error records with updated field mappings."""
    event_id = str(data.get("event_id", "")).strip()
    mapper = data.get("mapper")
    if not event_id or not isinstance(mapper, dict):
        raise ValueError("event_id and mapper are required")
    records = list_rejected(event_id)["records"]
    if data.get("rows") and isinstance(data["rows"], list):
        rows = data["rows"]
    else:
        selected_numbers = {int(value) for value in data.get("row_numbers", [])}
        rows = [
            record["raw_record"] for record in records if not selected_numbers or record["row_number"] in selected_numbers
        ]
    if not rows:
        raise ValueError("No rejected records were found for reprocessing")

    if records:
        first_rec = records[0]
        if not mapper.get("business_id") and first_rec.get("business_id"):
            mapper["business_id"] = first_rec["business_id"]
        if not mapper.get("source_type_id") and first_rec.get("source_type_id"):
            mapper["source_type_id"] = first_rec["source_type_id"]
        if not mapper.get("brand") and mapper.get("business_id"):
            try:
                for b in fetch_mirror_businesses():
                    if b.get("business_id") == mapper["business_id"]:
                        mapper["brand"] = b.get("name")
                        break
            except Exception:
                pass

    source_fields = sorted({path for path in mapper.get("fields", {}).values() if path})
    if not source_fields and rows and isinstance(rows[0], dict):
        source_fields = list(rows[0].keys())

    reprocessed_row_numbers = [int(v) for v in data.get("row_numbers", [])]
    if not reprocessed_row_numbers and records:
        reprocessed_row_numbers = [int(rec["row_number"]) for rec in records if "row_number" in rec]

    result = ws.save_mapper({
        "mapper": mapper,
        "rows": rows,
        "source_fields": source_fields,
        "save_template": False,
        "event_id": event_id,
        "row_offset": (reprocessed_row_numbers[0] - 1) if len(reprocessed_row_numbers) == 1 else 0,
    })

    result["error_listings_cleanup"] = {
        "attempted": bool(records and reprocessed_row_numbers),
        "ok": True,
        "rows_updated": 0,
    }
    if records and reprocessed_row_numbers:
        try:
            project_id, dataset_id, credentials_json = ws._warehouse_settings()
            client = ws._bigquery_client(project_id, credentials_json)
            from google.cloud import bigquery

            update_query = f"""
            UPDATE `{project_id}.{dataset_id}.error_listings`
            SET is_deleted = TRUE, deleted_on = CURRENT_TIMESTAMP()
            WHERE event_id = @event_id AND row_number IN UNNEST(@row_numbers)
            """
            update_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("event_id", "STRING", event_id),
                    bigquery.ArrayQueryParameter("row_numbers", "INT64", reprocessed_row_numbers),
                ]
            )
            update_job = client.query(update_query, job_config=update_config)
            update_job.result()
            rows_updated = update_job.num_dml_affected_rows or 0
            result["error_listings_cleanup"]["rows_updated"] = rows_updated
            if rows_updated < len(reprocessed_row_numbers):
                ws.LOGGER.warning(
                    "error_listings_cleanup_incomplete event_id=%s expected=%d updated=%d row_numbers=%s",
                    event_id,
                    len(reprocessed_row_numbers),
                    rows_updated,
                    reprocessed_row_numbers,
                )
                result["error_listings_cleanup"]["ok"] = False
        except Exception as exc:
            ws.LOGGER.exception(
                "error_listings_cleanup_failed event_id=%s row_numbers=%s", event_id, reprocessed_row_numbers
            )
            result["error_listings_cleanup"] = {"attempted": True, "ok": False, "rows_updated": 0, "error": str(exc)}

    return result


def error_listings_by_brand() -> dict[str, Any]:
    """Per-brand breakdown of how many (non-deleted) error listings each business has."""
    project_id, dataset_id, credentials_json = ws._warehouse_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    query = f"""
    SELECT
      e.business_id AS business_id,
      COALESCE(b.name, e.business_id) AS brand,
      COUNT(*) AS count
    FROM `{project_id}.{dataset_id}.error_listings` e
    LEFT JOIN `{project_id}.{dataset_id}.businesses` b
      ON b.business_id = e.business_id AND b.is_deleted IS NOT TRUE
    WHERE e.is_deleted IS NOT TRUE
    GROUP BY business_id, brand
    ORDER BY count DESC
    """
    try:
        rows = [
            {"business_id": row["business_id"], "brand": row["brand"], "count": int(row["count"])}
            for row in client.query(query).result()
        ]
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            return {"brands": [], "total": 0}
        raise
    return {"brands": rows, "total": sum(row["count"] for row in rows)}
