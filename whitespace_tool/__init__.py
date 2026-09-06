"""Competitive Whitespace Tool & Location Intelligence Platform.

Modular Subpackages:
- whitespace_tool.common: Core data models, I/O helpers, field registries, normalization, & configuration loaders.
- whitespace_tool.persistence: Data warehouse BigQuery integration, schema definitions, & SQLite caching mirror.
- whitespace_tool.analytics: Spatial whitespace calculation, data quality validation, learning algorithms, & sample datasets.
- whitespace_tool.cli: Command-line interface runner & entry points.
- whitespace_tool.auth: User authentication & credential verification.
- whitespace_tool.mapping: Target schemas, custom fields, data source previews & dataset ingestion.
- whitespace_tool.review: Data validation error listings & record reprocessing.
- whitespace_tool.templates: Built-in brand templates & workflow template catalog.
- whitespace_tool.system: Storage health probes, dataset clearing, medallion ETL & scheduler.
- whitespace_tool.reporting: Whitespace analytics, market share reporting, & geographic lookup.
- whitespace_tool.workflow_server: HTTP server & web application entry point.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
