"""Facade module re-exporting SQLite caching operations from whitespace_tool.persistence.sqlite_cache."""

from whitespace_tool.persistence.sqlite_cache import (
    fetch_mirror_businesses,
    fetch_mirror_reporting_locations,
    fetch_mirror_reporting_locations_by_brand,
    fetch_mirror_zip_brand_activity,
    get_cached_query,
    get_mirror_status,
    invalidate_cache,
    replace_gold_mirror,
    set_cached_query,
)

__all__ = [
    "fetch_mirror_businesses",
    "fetch_mirror_reporting_locations",
    "fetch_mirror_reporting_locations_by_brand",
    "fetch_mirror_zip_brand_activity",
    "get_cached_query",
    "get_mirror_status",
    "invalidate_cache",
    "replace_gold_mirror",
    "set_cached_query",
]

