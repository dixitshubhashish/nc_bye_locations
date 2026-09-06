from datetime import datetime, timedelta
import json
from pyodide.http import pyfetch
import random


async def get_restaurants():
    url = "https://overpass-api.de/api/interpreter"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    overpass_query = """
    [out:json][timeout:30];
    node["amenity"="restaurant"](33.70, -118.50, 34.30, -117.90);
    out 1000;
    """
    response = await pyfetch(url, method="POST", headers=headers, body=f"data={overpass_query}")
    if response.status != 200:
        raise RuntimeError(f"Request failed ({response.status}): {await response.string()}")
    payload = await response.json()
    elements = payload.get("elements", [])
    if not elements:
        return []

    selected_elements = random.sample(elements, min(len(elements), random.randint(400, 500)))
    base_date = datetime(2022, 1, 1)
    records = []
    for element in selected_elements:
        tags = element.get("tags", {})
        lat, lon, osm_id = element.get("lat"), element.get("lon"), element.get("id")
        name = tags.get("name") or tags.get("brand") or "Independent Diner"
        cuisine = tags.get("cuisine", "American").split(";")[0].capitalize()
        street = tags.get("addr:street", "")
        number = tags.get("addr:housenumber", "")
        address = f"{number} {street}".strip() if street else "Downtown Boulevard"
        city = tags.get("addr:city", "Los Angeles")
        state = tags.get("addr:state", "CA")
        postal_code = tags.get("addr:postcode", "90001")
        district = tags.get("addr:district") or tags.get("addr:suburb") or "Central"
        avg_ticket = round(random.uniform(14.0, 78.0), 2)
        daily_footfall = random.randint(120, 850)
        rental_cost = round(random.uniform(4500, 18000), 2)
        opening_date = (base_date + timedelta(days=random.randint(0, 1400))).strftime("%Y-%m-%d")
        records.append({
            "annual_revenue": round(daily_footfall * 30 * avg_ticket * random.uniform(10.5, 12.5), 2),
            "average_household_income": random.randint(52000, 145000),
            "average_ticket_size": avg_ticket,
            "city": city,
            "competitor_count": random.randint(1, 15),
            "concept_type": random.choice(["Casual Dining", "Fast Casual", "Fine Dining", "Quick Service"]),
            "country": "United States",
            "cuisine_type": cuisine,
            "daily_footfall": daily_footfall,
            "district": district,
            "foot_traffic_score": round(random.uniform(55.0, 99.0), 1),
            "franchise_name": tags.get("brand", "Independent"),
            "google_maps_link": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
            "latitude": lat,
            "lease_cost": rental_cost,
            "location_id": f"LOC-{osm_id}",
            "longitude": lon,
            "monthly_footfall": daily_footfall * 30,
            "neighborhood": tags.get("addr:suburb", district),
            "observed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "opening_date": opening_date,
            "operating_hours": tags.get("opening_hours", "10:00-22:00"),
            "parking_availability": random.choice(["Street", "Valet", "Dedicated Lot", "None"]),
            "phone_number": tags.get("phone") or tags.get("contact:phone") or "N/A",
            "population_density": random.randint(1500, 9500),
            "province": state,
            "ratings": round(random.uniform(3.2, 4.9), 1),
            "rental_cost": rental_cost,
            "name": name,
            "seating_capacity": random.randint(25, 240),
            "service_types": random.choice(["Dine-in, Takeout", "Dine-in Only", "Delivery, Takeout"]),
            "social_media_handles": f"@{name.lower().replace(' ', '')}_official",
            "state": state,
            "status": "Active",
            "address": address,
            "town": city,
            "website_url": tags.get("website") or tags.get("contact:website") or "",
            "postal_code": postal_code,
            "ddates": opening_date,
            "memberlevel": random.choice(["Gold", "Platinum", "Standard"]),
            "testloyaltytier": random.choice(["Tier 1", "Tier 2", "Tier 3"]),
            "fgsgdfhds": f"meta_{osm_id}",
        })
    return records


result = await get_restaurants()
