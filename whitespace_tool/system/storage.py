"""Storage connection testing and dataset maintenance.

Contains methods for probing database connectivity, verifying health checks,
and executing dataset table soft-deletions and truncations.
"""

from __future__ import annotations

from typing import Any

import whitespace_tool.workflow_server as ws
from whitespace_tool.persistence.sqlite_cache import invalidate_cache
from whitespace_tool.persistence.warehouse_bigquery import clear_dataset_tables


def _write_connection_health_probe(client: Any, project_id: str, dataset_id: str) -> dict[str, Any]:
    """Execute health probe query creating connection_health table in warehouse dataset."""
    table_ref = f"{project_id}.{dataset_id}.connection_health"
    client.query(f"""
    CREATE OR REPLACE TABLE `{table_ref}` AS
    SELECT
      'storage_connection' AS probe_name,
      CURRENT_TIMESTAMP() AS checked_at,
      1 AS ok
    """).result()
    rows = list(client.query(f"SELECT ok FROM `{table_ref}` LIMIT 1").result())
    if not rows or rows[0]["ok"] != 1:
        raise RuntimeError("Connection health probe table did not return the expected row")
    return {"table": table_ref, "rows": 1}


def test_storage_connection() -> dict[str, Any]:
    """Test BigQuery warehouse connection and verify US ZIP reference readiness."""
    project_id, dataset_id, credentials_json = ws._warehouse_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    ws._ensure_dataset(client, project_id, dataset_id)
    health = _write_connection_health_probe(client, project_id, dataset_id)
    zips = ws.prepare_zipcodes()
    probe = list(client.query("SELECT 1 AS ok").result())
    if not probe or probe[0]["ok"] != 1:
        raise RuntimeError("Workspace readiness check did not return the expected result")
    return {
        "ok": True,
        "status": "ready",
        "health": health,
        "zips": zips,
    }


def ping_storage_connection() -> dict[str, Any]:
    """Execute quick ping health check against warehouse storage."""
    project_id, dataset_id, credentials_json = ws._warehouse_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    ws._ensure_dataset(client, project_id, dataset_id)
    health = _write_connection_health_probe(client, project_id, dataset_id)
    probe = list(client.query("SELECT 1 AS ok").result())
    if not probe or probe[0]["ok"] != 1:
        raise RuntimeError("Readiness check did not return the expected result")
    return {
        "ok": True,
        "status": "ready",
        "health": health,
    }


def clear_saved_data() -> dict[str, Any]:
    """Clear all saved user business records and reset dataset tables."""
    project_id, dataset_id, credentials_json = ws._warehouse_settings()
    clear_result = clear_dataset_tables(project_id, dataset_id, credentials_json)
    deleted = clear_result["soft_deleted_tables"]
    truncated = clear_result["truncated_tables"]
    ws.ZIP_REFERENCE_CACHE.pop((project_id, dataset_id), None)
    invalidate_cache()
    return {
        "dataset": f"{project_id}.{dataset_id}",
        "deleted_tables": deleted,
        "deleted_count": len(deleted),
        "truncated_tables": truncated,
        "truncated_count": len(truncated),
    }
