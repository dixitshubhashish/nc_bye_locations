"""Facade module re-exporting field normalization utilities from whitespace_tool.common.normalization."""

from whitespace_tool.common.normalization import (
    clean_zip_code,
    get_nested,
    load_mapper,
    normalize_location,
    optional_date,
    optional_float,
    optional_int,
    optional_timestamp,
)

__all__ = [
    "clean_zip_code",
    "get_nested",
    "load_mapper",
    "normalize_location",
    "optional_date",
    "optional_float",
    "optional_int",
    "optional_timestamp",
]

