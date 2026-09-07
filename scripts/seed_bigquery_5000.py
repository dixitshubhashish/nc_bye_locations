# #!/usr/bin/env python3
# """Direct BigQuery Seeder: 20,000 - 25,000 Records with all 38 mapped fields.
#
# Features:
# - Exclusively target isolated dataset: 'sample_locations'
# - Plain tables ONLY: No partitioning, no clustering
# - Drops existing tables if they exist before recreating
# - 1,000 Faker brands (seeded into businesses table)
# - 1,000 Faker cities & 1,000 Faker street names
# - Half-and-half model:
#     - 50% realistic US location & performance data
#     - 50% synthetic / bad data angle (5-character alphanumeric ZIPs, Berlin/global zips,
#       random global lat/long coordinates, city/state/country mismatches)
# - All 38 canonical target fields populated and strongly typed
#
# Usage:
#     python scripts/seed_bigquery_5000.py
# or in Jupyter:
#     %run scripts/seed_bigquery_5000.py
# """
#
# import os
# import json
# import uuid
# import random
# import string
# import re
# from datetime import datetime, timezone, timedelta
# from pathlib import Path
# import pandas as pd
# from google.cloud import bigquery
# from google.oauth2 import service_account
# from faker import Faker
#
# # Determine project root
# ROOT_DIR = Path(__file__).resolve().parent.parent
#
# # Hardcoded project and isolated dataset (does not read from standard constants or env references)
# PROJECT_ID = "keen-device-610"
# DATASET_ID = "sample_locations"
# CREDENTIALS_FILE = str(ROOT_DIR / "config" / "connections" / "keen-device-610-2af9b27dfda3.json")
#
# # Target record volume (between 20,000 and 25,000)
# NUM_RECORDS = 22500
# NUM_BRANDS = 1000
# NUM_CITIES = 1000
# NUM_STREETS = 1000
#
# fake = Faker()
# Faker.seed(42)
# random.seed(42)
#
#
# def get_client() -> bigquery.Client:
#     """Initialize BigQuery client."""
#     if os.path.exists(CREDENTIALS_FILE):
#         credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE)
#         return bigquery.Client(project=PROJECT_ID, credentials=credentials)
#     return bigquery.Client(project=PROJECT_ID)
#
#
# def drop_and_recreate_tables(client: bigquery.Client) -> None:
#     """Drop existing tables if they exist, then recreate as plain tables (no partition, no cluster)."""
#     print(f"Ensuring dataset `{PROJECT_ID}.{DATASET_ID}` exists...")
#     dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
#     dataset_ref.location = "US"
#     client.create_dataset(dataset_ref, exists_ok=True)
#     print(f"✓ Dataset `{PROJECT_ID}.{DATASET_ID}` ready.")
#
#     tables = ["listings", "businesses", "source_types"]
#     for tbl in tables:
#         print(f"Dropping `{PROJECT_ID}.{DATASET_ID}.{tbl}` if exists...")
#         client.query(f"DROP TABLE IF EXISTS `{PROJECT_ID}.{DATASET_ID}.{tbl}`").result()
#         print(f"✓ Dropped `{tbl}`.")
#
#     # 1. Plain source_types table
#     ddl_source_types = f"""
#     CREATE TABLE `{PROJECT_ID}.{DATASET_ID}.source_types` (
#       source_type_id STRING NOT NULL,
#       name STRING NOT NULL,
#       data_format STRING,
#       created_at TIMESTAMP,
#       content_hash STRING
#     );
#     """
#     client.query(ddl_source_types).result()
#     print("✓ Created plain table `source_types` (no partition / no cluster).")
#
#     # 2. Plain businesses table
#     ddl_businesses = f"""
#     CREATE TABLE `{PROJECT_ID}.{DATASET_ID}.businesses` (
#       business_id STRING NOT NULL,
#       name STRING NOT NULL,
#       slug STRING NOT NULL,
#       source_type_id STRING,
#       description STRING,
#       logo_url STRING,
#       website_url STRING,
#       status STRING NOT NULL,
#       created_at TIMESTAMP,
#       updated_at TIMESTAMP,
#       meta_title STRING,
#       meta_description STRING,
#       country_of_origin STRING,
#       is_reference_data BOOL DEFAULT FALSE,
#       reference_key STRING,
#       default_source_url STRING,
#       default_source_name STRING,
#       is_sample_data BOOL DEFAULT TRUE,
#       sample_batch_id STRING,
#       content_hash STRING,
#       is_deleted BOOL DEFAULT FALSE,
#       deleted_on TIMESTAMP
#     );
#     """
#     client.query(ddl_businesses).result()
#     print("✓ Created plain table `businesses` (no partition / no cluster).")
#
#     # 3. Plain listings table (strictly NO PARTITION BY, NO CLUSTER BY)
#     ddl_listings = f"""
#     CREATE TABLE `{PROJECT_ID}.{DATASET_ID}.listings` (
#       listing_id STRING NOT NULL,
#       business_id STRING NOT NULL,
#       source_type_id STRING NOT NULL,
#       location_key STRING NOT NULL,
#       name STRING NOT NULL,
#       address STRING NOT NULL,
#       city_name STRING NOT NULL,
#       town STRING,
#       state_code STRING NOT NULL,
#       province STRING,
#       zip_code STRING NOT NULL,
#       country STRING,
#       latitude FLOAT64,
#       longitude FLOAT64,
#       first_observed_at TIMESTAMP,
#       last_observed_at TIMESTAMP,
#       template_id STRING,
#       ingestion_id STRING,
#       mapping_id STRING,
#       validation_status STRING,
#       is_sample_data BOOL DEFAULT TRUE,
#       sample_batch_id STRING,
#       franchise_name STRING,
#       concept_type STRING,
#       cuisine_type STRING,
#       neighborhood STRING,
#       district STRING,
#       phone_number STRING,
#       website_url STRING,
#       google_maps_link STRING,
#       social_media_handles STRING,
#       operating_hours STRING,
#       seating_capacity INT64,
#       service_types STRING,
#       opening_date DATE,
#       status STRING,
#       annual_revenue FLOAT64,
#       average_ticket_size FLOAT64,
#       daily_footfall INT64,
#       monthly_footfall INT64,
#       rental_cost FLOAT64,
#       lease_cost FLOAT64,
#       population_density FLOAT64,
#       average_household_income FLOAT64,
#       competitor_count INT64,
#       foot_traffic_score FLOAT64,
#       parking_availability STRING,
#       ratings FLOAT64,
#       content_hash STRING,
#       is_deleted BOOL DEFAULT FALSE,
#       deleted_on TIMESTAMP
#     );
#     """
#     client.query(ddl_listings).result()
#     print("✓ Created plain table `listings` (no partition / no cluster).")
#
#
# def seed_source_types(client: bigquery.Client) -> None:
#     """Populate source_types reference records."""
#     data = [
#         {"source_type_id": "csv", "name": "CSV Source", "data_format": json.dumps({"type": "flat_file"}), "created_at": datetime.now(timezone.utc), "content_hash": "src_csv"},
#         {"source_type_id": "json", "name": "JSON API Source", "data_format": json.dumps({"type": "nested_json"}), "created_at": datetime.now(timezone.utc), "content_hash": "src_json"}
#     ]
#     df = pd.DataFrame(data)
#     client.load_table_from_dataframe(
#         df, f"{PROJECT_ID}.{DATASET_ID}.source_types",
#         job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
#     ).result()
#     print("✓ Seeded source_types reference records.")
#
#
# def generate_and_seed_brands(client: bigquery.Client, count: int = NUM_BRANDS) -> list:
#     """Generate 1,000 realistic + synthetic brands (strictly excluding demo brands like Domino's, Pizza Hut, Little Caesars)."""
#     print(f"Generating and seeding {count} brands into `{PROJECT_ID}.{DATASET_ID}.businesses`...")
#     now = datetime.now(timezone.utc)
#     brands = []
#     rows = []
#
#     # Prohibited brands to prevent overlapping with demo/benchmark mapping datasets
#     FORBIDDEN = ["domino", "pizza hut", "little caesar", "subway", "starbucks", "mcdonald", "burger king", "wendy", "kfc"]
#     suffixes = ["Bistro", "Cafe", "Grill", "Kitchen", "Diner", "Bakery", "Burgers", "Tacos", "Express", "Roastery", "Bar & Bites", "Trattoria", "Eatery", "Steakhouse", "Pizzeria"]
#
#     i = 1
#     used_names = set()
#     while len(brands) < count:
#         if i % 2 == 0:
#             candidate_name = f"{fake.last_name()} {random.choice(suffixes)}"
#         else:
#             candidate_name = f"{fake.company().split()[0]} {random.choice(suffixes)}"
#
#         # Check against forbidden demo names
#         lower_name = candidate_name.lower()
#         if any(f in lower_name for f in FORBIDDEN) or candidate_name in used_names:
#             i += 1
#             continue
#
#         used_names.add(candidate_name)
#         biz_id = f"biz_brand_{len(brands) + 1:04d}"
#         slug = re.sub(r'[^a-zA-Z0-9]+', '-', candidate_name.lower()).strip('-')
#         clean_prefix = re.sub(r'[^A-Z0-9]', '', candidate_name.upper())[:4] or f"B{len(brands) + 1}"
#         src_id = random.choice(["csv", "json"])
#
#         brands.append({"biz_id": biz_id, "name": candidate_name, "prefix": clean_prefix, "src_id": src_id})
#         rows.append({
#             "business_id": biz_id, "name": candidate_name, "slug": slug, "source_type_id": src_id,
#             "description": f"{candidate_name} Independent Multi-Unit Chain", "status": "active",
#             "created_at": now, "updated_at": now,
#             "country_of_origin": random.choice(["USA", "Canada", "UK", "Germany", "France", "Japan", "Australia"]),
#             "is_sample_data": True, "sample_batch_id": f"batch_seed_{NUM_RECORDS}", "is_deleted": False
#         })
#         i += 1
#
#     df_biz = pd.DataFrame(rows)
#     client.load_table_from_dataframe(
#         df_biz, f"{PROJECT_ID}.{DATASET_ID}.businesses",
#         job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
#     ).result()
#     print(f"✓ Seeded {len(df_biz)} distinct non-demo businesses into `{PROJECT_ID}.{DATASET_ID}.businesses`.")
#     return brands
#
#
# def generate_listings(brands: list, total_records: int = NUM_RECORDS) -> pd.DataFrame:
#     """Generate 20,000 - 25,000 listings across all 38 fields using a half-half model."""
#     print(f"Generating {total_records} records with 1,000 cities & streets pools...")
#
#     # Pre-generate 1,000 cities and 1,000 street names
#     cities_pool = [fake.city() for _ in range(NUM_CITIES)]
#     streets_pool = [fake.street_name() for _ in range(NUM_STREETS)]
#
#     # 50 US standard states
#     US_STATES = [
#         "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
#         "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
#         "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
#         "VA", "WA", "WV", "WI", "WY"
#     ]
#
#     # Realistic benchmark metros for 50% accurate cluster
#     US_METROS = [
#         {"city": "New York", "town": "Manhattan", "state": "NY", "zip": "10001", "lat": 40.7505, "lon": -73.9965},
#         {"city": "Los Angeles", "town": "Downtown", "state": "CA", "zip": "90012", "lat": 34.0620, "lon": -118.2437},
#         {"city": "Chicago", "town": "Loop", "state": "IL", "zip": "60601", "lat": 41.8864, "lon": -87.6186},
#         {"city": "Houston", "town": "Midtown", "state": "TX", "zip": "77002", "lat": 29.7544, "lon": -95.3677},
#         {"city": "Phoenix", "town": "Central", "state": "AZ", "zip": "85004", "lat": 33.4532, "lon": -112.0738},
#         {"city": "Philadelphia", "town": "Center City", "state": "PA", "zip": "19102", "lat": 39.9534, "lon": -75.1661},
#         {"city": "San Antonio", "town": "Downtown", "state": "TX", "zip": "78205", "lat": 29.4243, "lon": -98.4871},
#         {"city": "San Diego", "town": "Gaslamp", "state": "CA", "zip": "92101", "lat": 32.7157, "lon": -117.1611},
#         {"city": "Dallas", "town": "Uptown", "state": "TX", "zip": "75201", "lat": 32.7877, "lon": -96.7997},
#         {"city": "Austin", "town": "Downtown", "state": "TX", "zip": "78701", "lat": 30.2711, "lon": -97.7437},
#         {"city": "Seattle", "town": "Capitol Hill", "state": "WA", "zip": "98101", "lat": 47.6101, "lon": -122.3344},
#         {"city": "Denver", "town": "LoDo", "state": "CO", "zip": "80202", "lat": 39.7538, "lon": -104.9986},
#         {"city": "Miami", "town": "Brickell", "state": "FL", "zip": "33131", "lat": 25.7681, "lon": -80.1901},
#         {"city": "Atlanta", "town": "Midtown", "state": "GA", "zip": "30309", "lat": 33.7925, "lon": -84.3857},
#         {"city": "Boston", "town": "Back Bay", "state": "MA", "zip": "02116", "lat": 42.3503, "lon": -71.0772}
#     ]
#
#     PARKING_OPTS = ["Dedicated Lot", "Street Parking", "Shared Plaza Lot", "Valet", "None / Pedestrian Only", "Garage"]
#     SERVICE_OPTS = ["Dine-in, Takeout, Delivery", "Takeout, Delivery", "Drive-thru, Takeout, Delivery", "Curbside Pickup"]
#     CONCEPT_OPTS = ["Quick Service Restaurant", "Fast Casual", "Casual Dining", "Ghost Kitchen", "Fine Casual"]
#     CUISINE_OPTS = ["Pizza & Italian", "Burgers & American", "Mexican Grill", "Asian Fusion", "Coffee & Bakery", "Sandwiches & Salads"]
#
#     # Global/International zip code styles for the bad data / synthetic half
#     INTERNATIONAL_ZIPS = [
#         "10115", "10117", "10178",  # Berlin, Germany
#         "SW1A 1AA", "EC1A 1BB", "W1A 0AX",  # London, UK
#         "M5V 2T6", "H2Y 1C6", "V6B 1A1",   # Canada
#         "75001", "75008", "69002",  # France
#         "2000", "3000", "4000",     # Australia
#         "100-0001", "160-0022"      # Japan
#     ]
#
#     now = datetime.now(timezone.utc)
#     records = []
#
#     for i in range(1, total_records + 1):
#         brand = random.choice(brands)
#         is_realistic = (i % 2 == 0)  # 50-50 half-half split
#
#         if is_realistic:
#             # --- Realistic Half: Consistent US Metro, 5-digit zip, bounding coords ---
#             metro = random.choice(US_METROS)
#             city_name = metro["city"]
#             town = metro["town"]
#             state_code = metro["state"]
#             province = f"{state_code} Region"
#             country = "USA"
#             zip_code = f"{int(metro['zip']) + random.randint(-50, 50):05d}"
#             lat = round(metro["lat"] + random.uniform(-0.08, 0.08), 6)
#             lon = round(metro["lon"] + random.uniform(-0.08, 0.08), 6)
#             phone = f"+1-{random.randint(200, 999)}-555-{random.randint(1000, 9999)}"
#         else:
#             # --- Bad Data / Synthetic Half: 1000 cities, alphanumeric/foreign zip, random global coords, mismatch ---
#             city_name = random.choice(cities_pool)
#             town = f"{fake.word().capitalize()} Ward"
#             state_code = random.choice(US_STATES)
#             province = fake.state()
#             country = random.choice(["USA", "Germany", "United Kingdom", "Canada", "Australia", "France", "Japan"])
#
#             # ZIP variation: 5-char alphanumeric, international zip, or random digits
#             zip_choice = random.randint(1, 3)
#             if zip_choice == 1:
#                 # 5-character alphanumeric (e.g., A1B2C, 9X4Y1)
#                 zip_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
#             elif zip_choice == 2:
#                 # International postal code (e.g. Berlin, London, Tokyo)
#                 zip_code = random.choice(INTERNATIONAL_ZIPS)
#             else:
#                 # Random 5-digit string (can have leading zeros)
#                 zip_code = f"{random.randint(500, 99999):05d}"
#
#             # Coordinates generated completely at random (unrestricted global coverage / test bad boundary)
#             lat = round(random.uniform(-55.0, 70.0), 6)
#             lon = round(random.uniform(-175.0, 175.0), 6)
#             phone = f"+{random.randint(1, 88)}-{random.randint(100, 999)}-{random.randint(100000, 999999)}"
#
#         # Street address using 1,000 streets pool
#         street_num = random.randint(1, 9999)
#         street_name = f"{street_num} {random.choice(streets_pool)}"
#
#         store_num = 10000 + i
#         location_key = f"{brand['prefix']}-{store_num}"
#
#         # Financial & footfall metrics
#         revenue = round(random.uniform(350000.0, 3500000.0), 2)
#         ticket_size = round(random.uniform(12.00, 48.00), 2)
#         daily_traffic = random.randint(90, 1400)
#         monthly_traffic = daily_traffic * 30
#         rent = round(random.uniform(2500.0, 22000.0), 2)
#         lease = round(rent * 12 * 1.05, 2)
#         rating = round(random.uniform(2.8, 5.0), 1)
#         traffic_score = round(random.uniform(40.0, 99.9), 1)
#         density = round(random.uniform(1500.0, 35000.0), 1)
#         income = round(random.uniform(45000.0, 160000.0), 2)
#
#         observed_time = now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23))
#         opening_date = (now - timedelta(days=random.randint(150, 6000))).strftime("%Y-%m-%d")
#
#         row = {
#             # Internal Keys & Audit
#             "listing_id": str(uuid.uuid4()),
#             "business_id": brand["biz_id"],
#             "source_type_id": brand["src_id"],
#             "template_id": f"tmpl_{brand['prefix'].lower()}_standard",
#             "ingestion_id": "ingest_direct_seed",
#             "mapping_id": "map_standard_38_fields",
#             "validation_status": "VALID" if is_realistic else "SYNTHETIC_TEST",
#             "is_sample_data": True,
#             "sample_batch_id": f"batch_seed_{total_records}",
#             "content_hash": f"hash_{location_key}_{i}",
#             "is_deleted": False,
#             "deleted_on": None,
#             "last_observed_at": observed_time,
#
#             # All 38 Canonical Mapped Fields
#             "location_key": location_key,                                   # 1. location_id
#             "name": f"{brand['name']} #{store_num}",                         # 2. name
#             "address": street_name,                                         # 3. address
#             "city_name": city_name,                                         # 4. city
#             "town": town,                                                   # 5. town
#             "state_code": state_code,                                       # 6. state
#             "province": province,                                           # 7. province
#             "zip_code": zip_code,                                           # 8. postal_code (random 5-digit or 5-char alphanumeric / foreign)
#             "country": country,                                             # 9. country
#             "latitude": lat,                                                # 10. latitude
#             "longitude": lon,                                               # 11. longitude
#             "franchise_name": f"{city_name} Hospitality Group {random.randint(1, 20)} LLC", # 12. franchise_name
#             "concept_type": random.choice(CONCEPT_OPTS),                    # 13. concept_type
#             "cuisine_type": random.choice(CUISINE_OPTS),                    # 14. cuisine_type
#             "neighborhood": f"{town} Sector {random.randint(1, 9)}",        # 15. neighborhood
#             "district": f"{city_name} District {random.randint(1, 12)}",    # 16. district
#             "phone_number": phone,                                          # 17. phone_number
#             "website_url": f"https://www.{brand['name'].lower().replace(' ', '').replace('&', '')}.com/locations/{location_key.lower()}", # 18. website_url
#             "google_maps_link": f"https://maps.google.com/?q={lat},{lon}", # 19. google_maps_link
#             "social_media_handles": f"@{brand['name'].lower().replace(' ', '').replace('&', '')}_{city_name.lower().replace(' ', '')}", # 20. social_media_handles
#             "operating_hours": random.choice(["Mon-Sun: 10:00-23:00", "Mon-Sun: 08:00-00:00", "24/7", "Tue-Sun: 11:00-22:00"]), # 21. operating_hours
#             "seating_capacity": int(random.choice([0, 16, 24, 36, 48, 64, 80, 120])), # 22. seating_capacity
#             "service_types": random.choice(SERVICE_OPTS),                   # 23. service_types
#             "opening_date": opening_date,                                   # 24. opening_date
#             "status": random.choice(["active", "active", "active", "temporarily_closed"]), # 25. status
#             "annual_revenue": revenue,                                      # 26. annual_revenue
#             "average_ticket_size": ticket_size,                             # 27. average_ticket_size
#             "daily_footfall": daily_traffic,                                # 28. daily_footfall
#             "monthly_footfall": monthly_traffic,                            # 29. monthly_footfall
#             "rental_cost": rent,                                            # 30. rental_cost
#             "lease_cost": lease,                                            # 31. lease_cost
#             "population_density": density,                                  # 32. population_density
#             "average_household_income": income,                             # 33. average_household_income
#             "competitor_count": random.randint(0, 12),                      # 34. competitor_count
#             "foot_traffic_score": traffic_score,                            # 35. foot_traffic_score
#             "parking_availability": random.choice(PARKING_OPTS),            # 36. parking_availability
#             "ratings": rating,                                              # 37. ratings
#             "first_observed_at": observed_time                              # 38. observed_at
#         }
#         records.append(row)
#
#     df = pd.DataFrame(records)
#     # Strongly type columns
#     df["seating_capacity"] = df["seating_capacity"].astype("Int64")
#     df["daily_footfall"] = df["daily_footfall"].astype("Int64")
#     df["monthly_footfall"] = df["monthly_footfall"].astype("Int64")
#     df["competitor_count"] = df["competitor_count"].astype("Int64")
#     df["latitude"] = df["latitude"].astype(float)
#     df["longitude"] = df["longitude"].astype(float)
#     df["opening_date"] = pd.to_datetime(df["opening_date"]).dt.date
#     df["first_observed_at"] = pd.to_datetime(df["first_observed_at"])
#     df["last_observed_at"] = pd.to_datetime(df["last_observed_at"])
#     return df
#
#
# def upload_listings(client: bigquery.Client, df: pd.DataFrame) -> None:
#     """Upload DataFrame to BigQuery `sample_locations.listings` as a plain table."""
#     table_id = f"{PROJECT_ID}.{DATASET_ID}.listings"
#     # Plain load config: Strictly NO partitioning, NO clustering
#     job_config = bigquery.LoadJobConfig(
#         write_disposition="WRITE_APPEND"
#     )
#     print(f"Uploading {len(df)} rows into `{table_id}` (plain unpartitioned table)...")
#     job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
#     job.result()
#     print(f"✅ Successfully loaded {job.output_rows} rows into `{table_id}`.")
#
#
# if __name__ == "__main__":
#     print(f"Connecting to BigQuery project: `{PROJECT_ID}`, target dataset: `{DATASET_ID}`...")
#     bq = get_client()
#
#     # 1. Drop existing tables if present, and recreate as plain tables
#     drop_and_recreate_tables(bq)
#
#     # 2. Seed source_types
#     seed_source_types(bq)
#
#     # 3. Generate and seed 1,000 brands into businesses table
#     brands_pool = generate_and_seed_brands(bq, count=NUM_BRANDS)
#
#     # 4. Generate 20,000 - 25,000 listings (half realistic, half synthetic/bad data) & upload
#     df_data = generate_listings(brands_pool, total_records=NUM_RECORDS)
#     upload_listings(bq, df_data)
#
#     print(f"\nAll done! Successfully loaded {len(df_data)} records into plain table `{PROJECT_ID}.{DATASET_ID}.listings`.")
