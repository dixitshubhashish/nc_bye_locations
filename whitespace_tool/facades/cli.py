"""Facade module re-exporting CLI entry points from whitespace_tool.cli.runner."""

from whitespace_tool.cli.runner import (
    build_parser,
    main,
    run_analyze,
    run_fetch_dominos,
    run_fetch_public_zips,
    run_push_bigquery,
    run_quality_check,
    run_workflow_ui,
)

__all__ = [
    "build_parser",
    "main",
    "run_analyze",
    "run_fetch_dominos",
    "run_fetch_public_zips",
    "run_push_bigquery",
    "run_quality_check",
    "run_workflow_ui",
]

