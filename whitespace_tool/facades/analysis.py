"""Facade module re-exporting analysis functionality from whitespace_tool.analytics.analysis."""

from whitespace_tool.analytics.analysis import (
    HAVERSINE_EARTH_RADIUS_MILES,
    analyze_whitespace,
    cluster_locations,
    deduplicate_locations,
    haversine_distance,
)

__all__ = [
    "HAVERSINE_EARTH_RADIUS_MILES",
    "analyze_whitespace",
    "cluster_locations",
    "deduplicate_locations",
    "haversine_distance",
]

