"""
Backend Compatibility Facades Package.

Centralizes backward-compatibility facade modules for location intelligence backend subpackages:
- common (config, field_registry, io, models, normalization, storage_config)
- persistence (sqlite_cache, warehouse_bigquery)
- analytics (analysis, data_quality, learning, sample_data)
- cli (runner)
"""

from whitespace_tool.facades import (
    analysis,
    cli,
    config,
    data_quality,
    field_registry,
    io,
    learning,
    models,
    normalization,
    sample_data,
    sqlite_cache,
    storage_config,
    warehouse_bigquery,
    workflow_server,
)

__all__ = [
    "analysis",
    "cli",
    "config",
    "data_quality",
    "field_registry",
    "io",
    "learning",
    "models",
    "normalization",
    "sample_data",
    "sqlite_cache",
    "storage_config",
    "warehouse_bigquery",
    "workflow_server",
]

