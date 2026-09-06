"""Facade module re-exporting data quality checks from whitespace_tool.analytics.data_quality."""

from whitespace_tool.analytics.data_quality import run_quality_checks

__all__ = [
    "run_quality_checks",
]

