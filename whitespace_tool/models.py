from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class LocationRecord:
    brand: str
    business_id: str | None
    source_type_id: str | None
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

    # Additional fields for enhanced location data
    franchise_name: str | None = None
    concept_type: str | None = None
    cuisine_type: str | None = None
    neighborhood: str | None = None
    district: str | None = None
    phone_number: str | None = None
    website_url: str | None = None
    google_maps_link: str | None = None
    social_media_handles: str | None = None  # JSON string or comma-separated
    operating_hours: str | None = None  # JSON string or formatted string
    seating_capacity: int | None = None
    service_types: str | None = None  # JSON string or comma-separated (dine-in, takeout, delivery, etc.)
    opening_date: str | None = None  # ISO date string
    status: str | None = None  # open, closed, temporarily_closed, etc.
    annual_revenue: float | None = None
    average_ticket_size: float | None = None
    daily_footfall: int | None = None
    monthly_footfall: int | None = None
    rental_cost: float | None = None
    lease_cost: float | None = None
    population_density: float | None = None  # people per sq mile or sq km
    average_household_income: float | None = None
    competitor_count: int | None = None  # number of competitors nearby
    foot_traffic_score: float | None = None  # 0-100 score
    parking_availability: str | None = None  # limited, ample, validated, etc.
    town: str | None = None
    province: str | None = None
    country: str | None = None

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