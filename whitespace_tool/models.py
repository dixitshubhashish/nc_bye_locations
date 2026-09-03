from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class LocationRecord:
    brand: str
    location_id: str
    name: str
    address: str
    city: str
    state: str
    postal_code: str
    latitude: float | None
    longitude: float | None
    source: str
    observed_at: str
    raw: dict[str, Any]

    @property
    def zip5(self) -> str:
        return self.postal_code[:5]


@dataclass(frozen=True)
class ZipDemographics:
    zip_code: str
    population: float | None
    median_household_income: float | None
    median_age: float | None
    source: str
    city: str | None = None
    county: str | None = None
    state_code: str | None = None
    state_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    households: float | None = None
    income_per_capita: float | None = None
    poverty: float | None = None
    employed_population: float | None = None
    unemployed_population: float | None = None
    housing_units: float | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
