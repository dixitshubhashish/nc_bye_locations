from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


SAMPLE_BATCH_ID = "sample_locations_v1"


@dataclass(frozen=True)
class SampleBrandConfig:
    key: str
    business_name: str
    source_type: str
    row_count: int
    error_rate: float
    geographies: tuple[str, ...]
    cuisine: str
    concept: str


SAMPLE_BRANDS: tuple[SampleBrandConfig, ...] = (
    SampleBrandConfig("dominos_pizza_api", "Domino's", "api_get_json", 720, 0.05, ("USA",), "Pizza", "Quick service"),
    SampleBrandConfig("pizza_hut_csv", "Pizza Hut", "csv", 680, 0.06, ("USA",), "Pizza", "Quick service"),
    SampleBrandConfig("little_caesars_json", "Little Caesars", "json", 620, 0.05, ("USA",), "Pizza", "Takeout pizza"),
    SampleBrandConfig("golden_fork_csv", "Golden Fork", "csv", 527, 0.06, ("USA", "Canada"), "American", "Casual dining"),
    SampleBrandConfig("urban_kitchen_json", "Urban Kitchen", "json", 650, 0.08, ("USA", "UK", "Germany"), "Modern European", "Urban cafe"),
    SampleBrandConfig("bella_italia_excel", "Bella Italia", "excel", 514, 0.06, ("USA", "Italy", "France"), "Italian", "Family restaurant"),
    SampleBrandConfig("sakura_sushi_api", "Sakura Sushi", "api_get_json", 750, 0.07, ("USA", "Japan", "Singapore"), "Japanese", "Sushi bar"),
    SampleBrandConfig("metro_bistro_osm", "Metro Bistro", "python_editor", 576, 0.07, ("USA", "UK"), "Bistro", "Neighborhood bistro"),
    SampleBrandConfig("spice_route_csv", "Spice Route", "csv", 680, 0.06, ("USA", "India"), "Indian", "Fast casual"),
    SampleBrandConfig("casa_verde_json", "Casa Verde", "json", 589, 0.07, ("USA", "Mexico"), "Mexican", "Fresh casual"),
    SampleBrandConfig("ocean_grill_excel", "Ocean Grill", "excel", 633, 0.06, ("USA", "Australia"), "Seafood", "Grill"),
    SampleBrandConfig("harvest_table_api", "Harvest Table", "api_get_json", 720, 0.07, ("USA", "Canada"), "Farm-to-table", "Casual dining"),
    SampleBrandConfig("local_table_osm", "Local Table", "python_editor", 568, 0.08, ("USA", "Germany"), "Cafe", "Local cafe"),
    SampleBrandConfig("fire_and_stone_csv", "Fire & Stone", "csv", 650, 0.06, ("USA", "UK"), "Pizza", "Wood-fired kitchen"),
    SampleBrandConfig("garden_kitchen_xml", "Garden Kitchen", "xml", 536, 0.06, ("USA", "Australia"), "Vegetarian", "Health focused"),
)


GEO_POINTS: tuple[dict[str, Any], ...] = (
    {"country": "USA", "city": "New York", "state": "NY", "postal": "10001", "lat": 40.7505, "lon": -73.9965},
    {"country": "USA", "city": "Austin", "state": "TX", "postal": "78701", "lat": 30.2711, "lon": -97.7437},
    {"country": "USA", "city": "Chicago", "state": "IL", "postal": "60601", "lat": 41.8864, "lon": -87.6186},
    {"country": "USA", "city": "Seattle", "state": "WA", "postal": "98101", "lat": 47.6101, "lon": -122.3344},
    {"country": "USA", "city": "Los Angeles", "state": "CA", "postal": "90001", "lat": 33.9731, "lon": -118.2479},
    {"country": "USA", "city": "Miami", "state": "FL", "postal": "33101", "lat": 25.7743, "lon": -80.1937},
    {"country": "USA", "city": "Atlanta", "state": "GA", "postal": "30301", "lat": 33.7490, "lon": -84.3880},
    {"country": "USA", "city": "Denver", "state": "CO", "postal": "80201", "lat": 39.7392, "lon": -104.9903},
    {"country": "USA", "city": "Phoenix", "state": "AZ", "postal": "85001", "lat": 33.4484, "lon": -112.0740},
    {"country": "USA", "city": "Dallas", "state": "TX", "postal": "75201", "lat": 32.7767, "lon": -96.7970},
    {"country": "USA", "city": "Philadelphia", "state": "PA", "postal": "19101", "lat": 39.9526, "lon": -75.1652},
    {"country": "USA", "city": "Charlotte", "state": "NC", "postal": "28201", "lat": 35.2271, "lon": -80.8431},
    {"country": "Canada", "city": "Toronto", "state": "ON", "postal": "M5H 2N2", "lat": 43.6532, "lon": -79.3832},
    {"country": "UK", "city": "London", "state": "England", "postal": "SW1A 1AA", "lat": 51.5072, "lon": -0.1276},
    {"country": "India", "city": "Mumbai", "state": "Maharashtra", "postal": "400001", "lat": 18.9388, "lon": 72.8354},
    {"country": "Australia", "city": "Sydney", "state": "NSW", "postal": "2000", "lat": -33.8688, "lon": 151.2093},
    {"country": "Germany", "city": "Berlin", "state": "Berlin", "postal": "10115", "lat": 52.52, "lon": 13.405},
    {"country": "France", "city": "Paris", "state": "Ile-de-France", "postal": "75001", "lat": 48.8566, "lon": 2.3522},
    {"country": "Japan", "city": "Tokyo", "state": "Tokyo", "postal": "100-0001", "lat": 35.6762, "lon": 139.6503},
    {"country": "Singapore", "city": "Singapore", "state": "Singapore", "postal": "018956", "lat": 1.2834, "lon": 103.8607},
    {"country": "Mexico", "city": "Mexico City", "state": "CDMX", "postal": "06000", "lat": 19.4326, "lon": -99.1332},
    {"country": "Italy", "city": "Rome", "state": "Lazio", "postal": "00186", "lat": 41.8931, "lon": 12.4828},
)


def stable_business_id(key: str) -> str:
    return f"sample_business_{key}"


def stable_template_id(key: str) -> str:
    return f"sample_template_{key}"


def source_label(source_type: str) -> str:
    return "OpenStreetMap" if source_type == "python_editor" else ("XLSX" if source_type == "excel" else source_type.upper())


def source_configuration(config: SampleBrandConfig) -> dict[str, Any]:
    label = source_label(config.source_type).lower()
    return {
        "source_name": f"{config.key}_{label}_sample",
        "mode": "sample",
        "source_type": config.source_type,
        "record_path": "locations" if config.source_type in {"json", "api_get_json"} else "",
        "is_sample_data": True,
    }


def mapper_for(config: SampleBrandConfig, business_id: str, source_type_id: str) -> dict[str, Any]:
    fields_by_type = {
        "csv": {
            "name": "restaurant_name", "address": "address", "city": "city_name", "state": "state_code",
            "postal_code": "postal_code", "location_id": "store_number", "country": "country",
            "latitude": "latitude", "longitude": "longitude", "franchise_name": "franchise_name",
            "concept_type": "concept_type", "cuisine_type": "cuisine_type", "phone_number": "phone",
            "website_url": "website", "google_maps_link": "maps_url", "social_media_handles": "social_handles",
        },
        "json": {
            "name": "location.name", "address": "location.address", "city": "location.city", "state": "location.state",
            "postal_code": "location.postalCode", "location_id": "location.id", "country": "location.country",
            "latitude": "geo.lat", "longitude": "geo.lng", "franchise_name": "brand.franchise",
            "concept_type": "brand.concept", "cuisine_type": "brand.cuisine", "neighborhood": "area.neighborhood",
            "district": "area.district", "phone_number": "contact.phone", "website_url": "contact.website",
            "social_media_handles": "contact.social",
        },
        "excel": {
            "name": "Restaurant", "address": "Street", "city": "Town", "state": "Province",
            "postal_code": "Post Code", "location_id": "Store ID", "country": "Country",
            "latitude": "Latitude", "longitude": "Longitude", "franchise_name": "Franchise",
            "concept_type": "Concept", "cuisine_type": "Cuisine", "phone_number": "Phone",
            "website_url": "Website", "google_maps_link": "Maps Link",
        },
        "api_get_json": {
            "name": "businessName", "address": "contact.address.street", "city": "contact.address.city",
            "state": "contact.address.region", "postal_code": "contact.address.postalCode",
            "location_id": "id", "country": "contact.address.country", "latitude": "coordinates.latitude",
            "longitude": "coordinates.longitude", "franchise_name": "categories.franchise",
            "concept_type": "categories.concept", "cuisine_type": "categories.cuisine",
            "phone_number": "contact.phone", "website_url": "contact.website",
        },
        "python_editor": {
            "name": "name", "address": "addr:street", "city": "addr:city", "state": "addr:state",
            "postal_code": "addr:postcode", "location_id": "osm_id", "country": "addr:country",
            "latitude": "lat", "longitude": "lon", "concept_type": "amenity", "cuisine_type": "cuisine",
            "phone_number": "phone", "website_url": "website",
        },
        "xml": {
            "name": "restaurant.name", "address": "restaurant.street", "city": "restaurant.city",
            "state": "restaurant.region", "postal_code": "restaurant.postal", "location_id": "restaurant.id",
            "country": "restaurant.country", "latitude": "restaurant.latitude", "longitude": "restaurant.longitude",
            "franchise_name": "restaurant.franchise", "concept_type": "restaurant.concept",
            "cuisine_type": "restaurant.cuisine", "phone_number": "restaurant.phone", "website_url": "restaurant.website",
        },
    }
    return {
        "brand": config.business_name,
        "business_id": business_id,
        "source_type": config.source_type,
        "source_type_id": source_type_id,
        "source_name": source_configuration(config)["source_name"],
        "fields": fields_by_type[config.source_type],
    }


def _geo_for(config: SampleBrandConfig, index: int) -> dict[str, Any]:
    choices = [geo for geo in GEO_POINTS if geo["country"] in config.geographies]
    return choices[index % len(choices)]


def _base_row(config: SampleBrandConfig, index: int, rng: random.Random) -> dict[str, Any]:
    geo = _geo_for(config, index)
    jitter = lambda scale: round(rng.uniform(-scale, scale), 6)
    store_id = f"{config.key.upper().replace('_', '-')}-{10000 + index}"
    name = f"{config.business_name} {geo['city']} {index % 37 + 1}"
    street_no = 100 + (index * 17) % 8900
    street = f"{street_no} {['Market', 'King', 'Oak', 'High', 'Station', 'Garden'][index % 6]} Street"
    return {
        "id": store_id,
        "name": name,
        "street": street,
        "city": geo["city"],
        "state": geo["state"],
        "postal": geo["postal"],
        "country": geo["country"],
        "lat": round(geo["lat"] + jitter(0.08), 6),
        "lon": round(geo["lon"] + jitter(0.08), 6),
        "phone": f"+1-555-{1000 + index % 9000}",
        "website": f"https://{config.key.replace('_', '')}.example.com/locations/{10000 + index}",
        "maps": f"https://maps.google.com/?q={geo['lat']},{geo['lon']}",
        "social": f"@{config.key.replace('_', '')}",
        "franchise": f"{config.business_name} Holdings",
        "concept": config.concept,
        "cuisine": config.cuisine,
        "neighborhood": ["Downtown", "Midtown", "Riverside", "Central", "West End"][index % 5],
        "district": ["North", "South", "East", "West", "Central"][index % 5],
    }


def _shape_row(config: SampleBrandConfig, base: dict[str, Any]) -> dict[str, Any]:
    if config.source_type == "csv":
        return {
            "restaurant_name": base["name"], "address": base["street"], "city_name": base["city"],
            "state_code": base["state"], "postal_code": base["postal"], "store_number": base["id"],
            "country": base["country"], "latitude": base["lat"], "longitude": base["lon"],
            "franchise_name": base["franchise"], "concept_type": base["concept"], "cuisine_type": base["cuisine"],
            "phone": base["phone"], "website": base["website"], "maps_url": base["maps"], "social_handles": base["social"],
        }
    if config.source_type == "json":
        return {
            "location": {"id": base["id"], "name": base["name"], "address": base["street"], "city": base["city"], "state": base["state"], "postalCode": base["postal"], "country": base["country"]},
            "geo": {"lat": base["lat"], "lng": base["lon"]},
            "brand": {"franchise": base["franchise"], "concept": base["concept"], "cuisine": base["cuisine"]},
            "area": {"neighborhood": base["neighborhood"], "district": base["district"]},
            "contact": {"phone": base["phone"], "website": base["website"], "social": base["social"]},
        }
    if config.source_type == "excel":
        return {
            "Store ID": base["id"], "Restaurant": base["name"], "Street": base["street"],
            "Town": base["city"], "Province": base["state"], "Post Code": base["postal"], "Country": base["country"],
            "Latitude": base["lat"], "Longitude": base["lon"], "Franchise": base["franchise"],
            "Concept": base["concept"], "Cuisine": base["cuisine"], "Phone": base["phone"],
            "Website": base["website"], "Maps Link": base["maps"],
        }
    if config.source_type == "api_get_json":
        return {
            "id": base["id"], "businessName": base["name"],
            "contact": {"address": {"street": base["street"], "city": base["city"], "region": base["state"], "postalCode": base["postal"], "country": base["country"]}, "phone": base["phone"], "website": base["website"]},
            "coordinates": {"latitude": base["lat"], "longitude": base["lon"]},
            "categories": {"franchise": base["franchise"], "concept": base["concept"], "cuisine": base["cuisine"]},
        }
    if config.source_type == "xml":
        return {
            "restaurant": {
                "id": base["id"], "name": base["name"], "street": base["street"], "city": base["city"],
                "region": base["state"], "postal": base["postal"], "country": base["country"],
                "latitude": base["lat"], "longitude": base["lon"], "franchise": base["franchise"],
                "concept": base["concept"], "cuisine": base["cuisine"], "phone": base["phone"], "website": base["website"],
            }
        }
    return {
        "osm_id": base["id"], "name": base["name"], "addr:street": base["street"], "addr:city": base["city"],
        "addr:state": base["state"], "addr:postcode": base["postal"], "addr:country": base["country"],
        "amenity": "restaurant", "cuisine": base["cuisine"], "lat": base["lat"], "lon": base["lon"],
        "phone": base["phone"], "website": base["website"],
    }


def _inject_error(config: SampleBrandConfig, row: dict[str, Any], index: int) -> None:
    if config.source_type == "csv":
        if index % 2:
            row["postal_code"] = ""
        else:
            row["website"] = "abc//restaurant"
    elif config.source_type == "json":
        row["geo"]["lat" if index % 2 else "lng"] = 143.992 if index % 2 else -245.22
    elif config.source_type == "excel":
        if index % 2:
            row["Store ID"] = f"{config.key.upper()}-DUPLICATE"
        else:
            row["Post Code"] = "ABCXYZ"
    elif config.source_type == "api_get_json":
        if index % 2:
            row["contact"]["address"] = {}
        else:
            row["contact"]["address"]["country"] = "USA"
            row["contact"]["address"]["region"] = "London"
    elif config.source_type == "python_editor":
        if index % 2:
            row["name"] = ""
        else:
            row["osm_id"] = f"{config.key.upper()}-DUPLICATE"
    else:
        row["restaurant"]["postal"] = "" if index % 2 else "ABCXYZ"


def generate_source_rows(config: SampleBrandConfig, source_type_id: str, batch_id: str = SAMPLE_BATCH_ID) -> list[dict[str, Any]]:
    rng = random.Random(f"{config.key}:2026")
    rows: list[dict[str, Any]] = []
    error_every = max(1, round(1 / max(config.error_rate, 0.01)))
    for index in range(config.row_count):
        row = _shape_row(config, _base_row(config, index, rng))
        if index % error_every == 0:
            _inject_error(config, row, index)
        row["__meta"] = {
            "template_id": stable_template_id(config.key),
            "ingestion_id": f"sample_ingestion_{config.key}_{batch_id}",
            "mapping_id": f"sample_mapping_{config.key}",
            "source_type_id": source_type_id,
            "is_sample_data": True,
            "sample_batch_id": batch_id,
        }
        rows.append(row)
    return rows
