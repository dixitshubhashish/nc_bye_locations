"""Core domain data models and datetime utilities.

Provides immutable dataclasses for normalized location records and ZIP-level
demographic data, alongside standardized ISO UTC timestamp generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class LocationRecord:
    """Normalized commercial location record representation.

    Attributes:
        brand: Name of the business brand or store chain.
        business_id: Unique identifier for the business entity.
        source_type_id: Data source type identifier.
        location_id: Unique identifier for the physical store location.
        name: Display name of the store location.
        address: Street address line.
        city: City or municipal boundary name.
        state: Two-character state code.
        postal_code: Full postal ZIP code string.
        latitude: Geographic latitude coordinate.
        longitude: Geographic longitude coordinate.
        source: Data provider source name.
        observed_at: Observation ISO timestamp string.
        raw: Raw ingestion payload data dictionary.
        franchise_name: Optional franchise group name.
        concept_type: Optional store format concept type.
        cuisine_type: Optional food service cuisine classification.
        neighborhood: Optional local neighborhood name.
        district: Optional administrative district.
        phone_number: Optional primary phone contact.
        website_url: Optional store URL link.
        google_maps_link: Optional Google Maps URI.
        social_media_handles: Optional social media handles JSON/text.
        operating_hours: Optional store opening schedule.
        seating_capacity: Optional seating capacity count.
        service_types: Optional service options (e.g. Delivery, Carryout).
        opening_date: Optional store inaugural opening date.
        status: Optional operational status indicator.
        annual_revenue: Optional estimated annual store revenue.
        average_ticket_size: Optional average transaction value.
        daily_footfall: Optional estimated daily visitor count.
        monthly_footfall: Optional estimated monthly visitor count.
        rental_cost: Optional monthly location lease/rent expense.
        lease_cost: Optional annual lease cost footprint.
        population_density: Optional trade area population density.
        average_household_income: Optional trade area average household income.
        competitor_count: Optional competitor count in immediate area.
        foot_traffic_score: Optional foot traffic rating index.
        parking_availability: Optional parking availability status.
        ratings: Optional customer rating score.
        town: Optional township name.
        province: Optional province or territory code.
        country: Optional country designation name.
    """

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
    social_media_handles: str | None = None
    operating_hours: str | None = None
    seating_capacity: int | None = None
    service_types: str | None = None
    opening_date: str | None = None
    status: str | None = None
    annual_revenue: float | None = None
    average_ticket_size: float | None = None
    daily_footfall: int | None = None
    monthly_footfall: int | None = None
    rental_cost: float | None = None
    lease_cost: float | None = None
    population_density: float | None = None
    average_household_income: float | None = None
    competitor_count: int | None = None
    foot_traffic_score: float | None = None
    parking_availability: str | None = None
    ratings: float | None = None
    town: str | None = None
    province: str | None = None
    country: str | None = None

    @property
    def zip5(self) -> str:
        """Extract the 5-digit US ZIP code prefix."""
        return self.postal_code[:5]


@dataclass(frozen=True)
class ZipDemographics:
    """US Census and demographic indicators for a 5-digit ZIP code area.

    Attributes:
        zip_code: 5-digit postal code string.
        population: Total resident population.
        median_household_income: Median household income currency value.
        median_age: Median resident age in years.
        source: Primary data source attribute label.
        city: Associated city name.
        county: Associated county or parish name.
        state_code: Two-character state postal abbreviation.
        state_name: Full state name.
        latitude: Geometric centroid latitude.
        longitude: Geometric centroid longitude.
        households: Total occupied housing units.
        income_per_capita: Per capita resident income value.
        poverty: Estimated population below poverty threshold.
        employed_population: Total employed civilian population count.
        unemployed_population: Total unemployed labor force count.
        housing_units: Total residential housing units count.
    """

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
    """Generate the current UTC timestamp formatted as a clean ISO 8601 string.

    Returns:
        ISO 8601 formatted UTC timestamp string without microseconds.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
