"""Template library services.

Contains logic for loading predefined templates, listing stored workflow templates,
and saving updated template versions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import whitespace_tool.workflow_server as ws


def predefined_templates() -> dict[str, Any]:
    """Load built-in brand template definitions from disk index."""
    root_dir = Path(__file__).resolve().parent.parent.parent
    template_index_path = root_dir / "config" / "predefined_brand_templates.json"
    if not template_index_path.exists():
        template_index_path = Path("config/predefined_brand_templates.json")
    with template_index_path.open("r", encoding="utf-8") as handle:
        templates = json.load(handle)
    for template in templates:
        t_path = Path(template["template_path"])
        if not t_path.is_absolute():
            t_path = root_dir / t_path
        with t_path.open("r", encoding="utf-8") as handle:
            mapper = json.load(handle)
        template["mapper"] = {
            "brand": template["brand"],
            "source_name": template["source_name"],
            "source_type": template["source_type"],
            "record_path": template.get("record_path", mapper.get("record_path", "")),
            "fields": mapper.get("fields", {}),
        }
    return {"templates": templates}


def list_templates(search: str = "", business_id: str = "", source_type_id: str = "") -> dict[str, Any]:
    """Query stored workflow templates matching search and filter parameters."""
    from google.cloud import bigquery

    project_id, dataset_id, credentials_json = ws._warehouse_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    ws._ensure_workflow_templates_table(client, project_id, dataset_id)
    query = f"""
    SELECT workflow_template_id, business_id, source_type_id, name, components, created_at, updated_at
    FROM `{project_id}.{dataset_id}.workflow_templates`
    WHERE is_deleted IS NOT TRUE
      AND (@search = '' OR LOWER(name) LIKE CONCAT('%', LOWER(@search), '%'))
      AND (@business_id = '' OR business_id = @business_id)
      AND (
        @source_type_id = ''
        OR source_type_id = @source_type_id
        OR JSON_VALUE(components, '$.source_type_id') = @source_type_id
        OR JSON_VALUE(components, '$.mapper.source_type_id') = @source_type_id
      )
    ORDER BY updated_at DESC
    LIMIT 100
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("search", "STRING", search),
            bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
            bigquery.ScalarQueryParameter("source_type_id", "STRING", source_type_id),
        ]
    )
    templates = []
    for row in client.query(query, job_config=config).result():
        item = dict(row)
        if hasattr(item.get("created_at"), "isoformat"):
            item["created_at"] = item["created_at"].isoformat()
        if hasattr(item.get("updated_at"), "isoformat"):
            item["updated_at"] = item["updated_at"].isoformat()
        if isinstance(item.get("components"), str):
            item["components"] = json.loads(item["components"])
        components = item.get("components") if isinstance(item.get("components"), dict) else {}
        mapper = components.get("mapper") if isinstance(components.get("mapper"), dict) else components
        item["template_id"] = item.get("workflow_template_id")
        item["template_name"] = item.get("name")
        item["source_type_id"] = (
            item.get("source_type_id") or components.get("source_type_id") or mapper.get("source_type_id")
        )
        item["source_type"] = mapper.get("source_type")
        item["status"] = item.get("status", "active")
        templates.append(item)
    return {"templates": templates}


def save_template_version(data: dict[str, Any]) -> dict[str, Any]:
    """Save an updated component payload version for a workflow template."""
    from google.cloud import bigquery

    template_id = str(data.get("workflow_template_id", "")).strip()
    components = data.get("components")
    if not template_id or not isinstance(components, dict):
        raise ValueError("workflow_template_id and components are required")
    project_id, dataset_id, credentials_json = ws._warehouse_settings()
    client = ws._bigquery_client(project_id, credentials_json)
    table_ref = f"{project_id}.{dataset_id}.workflow_templates"
    ws._ensure_workflow_templates_table(client, project_id, dataset_id)
    mapper = components.get("mapper") if isinstance(components.get("mapper"), dict) else components
    source_type_id = str(components.get("source_type_id") or mapper.get("source_type_id") or "").strip() or None
    query = f"UPDATE `{table_ref}` SET archived_components = components, components = @components, source_type_id = @source_type_id, updated_at = CURRENT_TIMESTAMP() WHERE workflow_template_id = @template_id"
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("template_id", "STRING", template_id),
            bigquery.ScalarQueryParameter("components", "JSON", json.dumps(components, sort_keys=True)),
            bigquery.ScalarQueryParameter("source_type_id", "STRING", source_type_id),
        ]
    )
    client.query(query, job_config=config).result()
    return {"workflow_template_id": template_id, "updated": True}

