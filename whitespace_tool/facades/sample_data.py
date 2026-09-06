"""Facade module re-exporting benchmark sample data generators from whitespace_tool.analytics.sample_data."""

from whitespace_tool.analytics.sample_data import (
    SAMPLE_BATCH_ID,
    SAMPLE_BRANDS,
    generate_source_rows,
    mapper_for,
    source_configuration,
    source_label,
    stable_business_id,
    stable_template_id,
)

__all__ = [
    "SAMPLE_BATCH_ID",
    "SAMPLE_BRANDS",
    "generate_source_rows",
    "mapper_for",
    "source_configuration",
    "source_label",
    "stable_business_id",
    "stable_template_id",
]

