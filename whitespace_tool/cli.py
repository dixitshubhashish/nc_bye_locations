from __future__ import annotations

import argparse
from pathlib import Path

from whitespace_tool.analysis import analyze_whitespace
from whitespace_tool.config import load_config
from whitespace_tool.data_quality import run_quality_checks
from whitespace_tool.io import write_csv, write_demographics_csv, write_json
from whitespace_tool.models import utc_now_iso
from whitespace_tool.sources.csv_locations import load_location_sources
from whitespace_tool.sources.demographics import load_demographics
from whitespace_tool.warehouse_bigquery import (
    build_table_rows,
    push_to_bigquery,
    write_bigquery_jsonl,
    write_bigquery_schema,
)
from whitespace_tool.storage_config import load_storage_config


def run_analysis(config_path: str, output_dir: str) -> None:
    config = load_config(config_path)
    locations = load_location_sources(config)
    demographics = load_demographics(config)
    location_rows, whitespace_rows, summary = analyze_whitespace(locations, demographics, config)

    out = Path(output_dir)
    write_csv(out / "brand_locations.csv", location_rows)
    write_csv(out / "whitespace_zips.csv", whitespace_rows)
    write_json(
        out / "run_manifest.json",
        {
            "config_path": str(config_path),
            "generated_at": utc_now_iso(),
            "outputs": {
                "brand_locations": "brand_locations.csv",
                "whitespace_zips": "whitespace_zips.csv",
            },
            "summary": summary,
            "sources": {
                "location_sources": config["location_sources"],
                "demographics_source": config["demographics_source"],
            },
            "limitations": config.get("limitations", []),
        },
    )
    print(f"Wrote {len(location_rows)} location rows and {len(whitespace_rows)} whitespace ZIP rows to {out}")


def fetch_public_zips(config_path: str, output_path: str, limit: int | None) -> None:
    from whitespace_tool.sources.public_us_zips_bigquery import fetch_from_bigquery

    demographics = fetch_from_bigquery(config_path, limit=limit)
    write_demographics_csv(output_path, demographics)
    print(f"Wrote {len(demographics)} public BigQuery ZIP rows to {output_path}")


def quality_check(config_path: str, output_dir: str) -> None:
    config = load_config(config_path)
    locations = load_location_sources(config)
    demographics = load_demographics(config)
    report = run_quality_checks(locations, demographics, config)
    out = Path(output_dir)
    write_json(out / "data_quality_report.json", report)
    write_csv(out / "data_quality_issues.csv", report["issues"])
    print(
        "Data quality "
        f"{'passed' if report['passed'] else 'failed'}: "
        f"{report['summary']['error_count']} errors, {report['summary']['warning_count']} warnings"
    )


def push_bigquery(
    config_path: str,
    project_id: str | None,
    dataset_id: str | None,
    stage_dir: str,
    dry_run: bool,
    credentials_json: str | None,
) -> None:
    config = load_config(config_path)
    storage = load_storage_config()
    project_id = project_id or storage.get("project_id")
    dataset_id = dataset_id or storage.get("bronze_dataset_id")
    credentials_json = credentials_json or storage.get("credentials_json")
    if credentials_json:
        credentials_path = Path(credentials_json)
        if not credentials_path.is_absolute():
            credentials_json = str(credentials_path)
    if not project_id or not dataset_id:
        raise RuntimeError("BigQuery project_id and dataset_id must be provided by args or config warehouse block.")

    locations = load_location_sources(config)
    demographics = load_demographics(config)
    report = run_quality_checks(locations, demographics, config)
    if not report["passed"]:
        raise RuntimeError("Data quality failed. Run quality-check and fix errors before pushing to BigQuery.")

    _, whitespace_rows, summary = analyze_whitespace(locations, demographics, config)
    rows_by_table = build_table_rows(locations, demographics, config, whitespace_rows, summary)
    write_bigquery_schema(stage_dir)
    write_bigquery_jsonl(stage_dir, rows_by_table)
    if dry_run:
        print(f"Wrote BigQuery-ready JSONL and schema files to {stage_dir}")
        return
    push_to_bigquery(project_id, dataset_id, rows_by_table, credentials_json)
    print(f"Pushed unified tables to BigQuery dataset {project_id}.{dataset_id}")


def serve_workflow_ui(host: str, port: int) -> None:
    from whitespace_tool.workflow_server import serve

    serve(host, port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Competitive whitespace analysis prototype")
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser("analyze", help="Run whitespace analysis outputs")
    analyze_parser.add_argument("--config", default="config/demo.json", help="Path to a JSON run configuration")
    analyze_parser.add_argument("--output-dir", default="outputs/demo", help="Directory for generated CSV/JSON outputs")

    public_zips_parser = subparsers.add_parser("fetch-public-zips", help="Fetch ZIP geography + ACS fields from BigQuery public data")
    public_zips_parser.add_argument("--config", default="config/connections/storage.json")
    public_zips_parser.add_argument("--output", default="data/us_zips_bigquery.csv")
    public_zips_parser.add_argument("--limit", type=int, default=None, help="Optional row limit for inspection")

    quality_parser = subparsers.add_parser("quality-check", help="Run data quality checks in one module")
    quality_parser.add_argument("--config", default="config/demo.json", help="Path to a JSON run configuration")
    quality_parser.add_argument("--output-dir", default="outputs/demo", help="Directory for quality reports")

    bq_parser = subparsers.add_parser("push-bigquery", help="Stage or push unified tables to BigQuery")
    bq_parser.add_argument("--config", default="config/demo.json", help="Path to a JSON run configuration")
    bq_parser.add_argument("--project-id", default=None, help="Google Cloud project id; falls back to config warehouse.project_id")
    bq_parser.add_argument("--dataset-id", default=None, help="BigQuery dataset id; falls back to config warehouse.dataset_id")
    bq_parser.add_argument("--stage-dir", default="outputs/bigquery", help="Local JSONL/schema staging directory")
    bq_parser.add_argument("--dry-run", action="store_true", help="Write BigQuery files locally without pushing")
    bq_parser.add_argument("--credentials-json", default=None, help="Optional service-account JSON path; ADC also works")

    workflow_ui_parser = subparsers.add_parser("workflow-ui", help="Serve the no-code workflow template UI")
    workflow_ui_parser.add_argument("--host", default="127.0.0.1")
    workflow_ui_parser.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()
    if args.command == "fetch-public-zips":
        fetch_public_zips(args.config, args.output, args.limit)
    elif args.command == "quality-check":
        quality_check(args.config, args.output_dir)
    elif args.command == "push-bigquery":
        push_bigquery(
            args.config,
            args.project_id,
            args.dataset_id,
            args.stage_dir,
            args.dry_run,
            args.credentials_json,
        )
    elif args.command == "workflow-ui":
        serve_workflow_ui(args.host, args.port)
    else:
        serve_workflow_ui("127.0.0.1", 8765)


if __name__ == "__main__":
    main()
