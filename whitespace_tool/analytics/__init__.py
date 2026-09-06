"""Analytics package providing whitespace analysis, data quality checks, template learning, and sample data generation."""

from whitespace_tool.analytics.analysis import (
    FUZZY_ADDRESS_MATCH_THRESHOLD,
    FUZZY_COORDINATE_TOLERANCE,
    analyze_whitespace,
    dedupe_location_key,
    dedupe_locations,
    is_fuzzy_duplicate_location,
)
from whitespace_tool.analytics.data_quality import US_STATE_CODES, run_quality_checks
from whitespace_tool.analytics.learning import suggest_from_templates
from whitespace_tool.analytics.sample_data import (
    GEO_POINTS,
    SAMPLE_BATCH_ID,
    SAMPLE_BRANDS,
    SampleBrandConfig,
    generate_source_rows,
    mapper_for,
    source_configuration,
    source_label,
    stable_business_id,
    stable_template_id,
)

__all__ = [
    "FUZZY_ADDRESS_MATCH_THRESHOLD",
    "FUZZY_COORDINATE_TOLERANCE",
    "GEO_POINTS",
    "SAMPLE_BATCH_ID",
    "SAMPLE_BRANDS",
    "US_STATE_CODES",
    "SampleBrandConfig",
    "analyze_whitespace",
    "dedupe_location_key",
    "dedupe_locations",
    "generate_source_rows",
    "is_fuzzy_duplicate_location",
    "mapper_for",
    "run_quality_checks",
    "source_configuration",
    "source_label",
    "stable_business_id",
    "stable_template_id",
    "suggest_from_templates",
]

