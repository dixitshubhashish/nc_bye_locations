"""Pure, dependency-free helpers for the reporting module.

These functions were moved out of :mod:`whitespace_tool.workflow_server` as
part of the reporting module segregation. They perform only in-memory work -
query-parameter parsing, metric math, and coordinate/brand/demographic
predicate checks - and import nothing from the server module, so they can be
imported anywhere without creating an import cycle.

Grouping:
    * Parameter parsing - :func:`_csv_param`, :func:`_safe_float`
    * Metric formulas    - :func:`_median`, :func:`_share_pct`,
      :func:`_pct_diff`, :func:`_population_per_location`
    * Row predicates     - :func:`_lat_lon_ok_or_null`,
      :func:`_lat_lon_ok_strict`, :func:`_passes_brand_filter`,
      :func:`_passes_demographic_filters`
"""
from __future__ import annotations

from typing import Any


def _csv_param(value: str) -> list[str]:
    """Split a comma-separated query-string value into a clean list.

    Args:
        value: Raw value such as ``"Domino's, Pizza Hut ,"``.

    Returns:
        The comma-separated items, individually stripped, with empty items
        dropped (e.g. ``["Domino's", "Pizza Hut"]``).
    """
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_float(value: Any) -> float | None:
    """Coerce a value to ``float``, tolerating blanks and bad input.

    Args:
        value: Any value, typically a raw query-string entry.

    Returns:
        The value as a ``float``, or ``None`` when it is ``None``/empty or
        cannot be parsed as a number.
    """
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Shared metric formulas reused across geo (state), brand, and brand-location
# levels so the same figure is never computed two different ways.
def _median(values: list[float]) -> float | None:
    """Return the (upper) median of ``values``.

    Uses the upper-middle element for even-length inputs (no averaging).

    Args:
        values: Numeric samples; may be empty.

    Returns:
        The median value, or ``None`` when ``values`` is empty.
    """
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _share_pct(part: float, whole: float) -> float:
    """Return ``part`` as a percentage of ``whole``, rounded to 1 decimal.

    Args:
        part: The subset count/measure.
        whole: The total the subset is measured against.

    Returns:
        The percentage share, or ``0.0`` when ``whole`` is not positive
        (guards against division by zero).
    """
    return round((part / whole) * 100, 1) if whole > 0 else 0.0


def _pct_diff(value: float, baseline: float) -> float:
    """Return the percentage difference of ``value`` from ``baseline``.

    Args:
        value: The observed value.
        baseline: The reference value; treated as at least ``1`` to avoid
            division by zero.

    Returns:
        ``((value - baseline) / max(baseline, 1)) * 100`` rounded to 1 decimal.
    """
    return round(((value - baseline) / max(baseline, 1)) * 100, 1)


def _population_per_location(population: float, locations: float) -> float:
    """Return people served per location (population / locations).

    Args:
        population: Total population for the area.
        locations: Number of locations in the area.

    Returns:
        The rounded population-per-location ratio, or ``population`` itself
        when ``locations`` is not positive.
    """
    return round(population / locations) if locations > 0 else population


def _lat_lon_ok_or_null(lat: float | None, lon: float | None) -> bool:
    """Lenient US-bounds coordinate check (missing coordinates allowed).

    Mirrors ``base_cte``'s "latitude IS NULL OR (latitude/longitude within US
    bounds)" rule: a missing coordinate passes through, but a coordinate that
    is present must fall inside the continental US / territory bounds.

    Args:
        lat: Latitude, or ``None`` if absent.
        lon: Longitude, or ``None`` if absent.

    Returns:
        ``True`` if the coordinate is absent or valid; ``False`` if a latitude
        is present without a longitude, or the pair is outside US bounds.
    """
    if lat is None:
        return True
    if lon is None:
        return False
    return 13.0 <= lat <= 72.0 and ((-180.0 <= lon <= -64.0) or (144.0 <= lon <= 146.0))


def _lat_lon_ok_strict(lat: float | None, lon: float | None) -> bool:
    """Strict US-bounds coordinate check (both coordinates required).

    Mirrors ``map_query``'s hard requirement that latitude and longitude are
    both present and within US bounds; unlike :func:`_lat_lon_ok_or_null`, a
    missing coordinate is excluded.

    Args:
        lat: Latitude, or ``None`` if absent.
        lon: Longitude, or ``None`` if absent.

    Returns:
        ``True`` only when both are present and inside US bounds.
    """
    if lat is None or lon is None:
        return False
    return 13.0 <= lat <= 72.0 and ((-180.0 <= lon <= -64.0) or (144.0 <= lon <= 146.0))


def _passes_brand_filter(brand_name: str | None, selected_brands: list[str]) -> bool:
    """Return whether a row's brand survives the selected-brand filter.

    Args:
        brand_name: The row's brand.
        selected_brands: The brands the user selected; an empty list means
            "no brand filter" and everything passes.

    Returns:
        ``True`` when no filter is active or ``brand_name`` is one of the
        selected brands.
    """
    return not selected_brands or brand_name in selected_brands


def _passes_demographic_filters(
    population: float | None, income: float | None, age: float | None,
    min_population: float | None, min_income: float | None, max_median_age: float | None,
) -> bool:
    """Return whether a row satisfies the demographic threshold filters.

    Each threshold is applied only when it is set (non-``None``); a missing
    row metric is treated as ``0`` for the comparison.

    Args:
        population: Row population; compared against ``min_population``.
        income: Row median household income; compared against ``min_income``.
        age: Row median age; compared against ``max_median_age``.
        min_population: Minimum population to keep, or ``None`` to skip.
        min_income: Minimum income to keep, or ``None`` to skip.
        max_median_age: Maximum median age to keep, or ``None`` to skip.

    Returns:
        ``True`` if the row passes every active threshold.
    """
    if min_population is not None and (population or 0) < min_population:
        return False
    if min_income is not None and (income or 0) < min_income:
        return False
    if max_median_age is not None and (age or 0) > max_median_age:
        return False
    return True
