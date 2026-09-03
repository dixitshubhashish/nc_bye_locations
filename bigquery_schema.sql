CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.states` (
  state_code STRING NOT NULL,
  state_name STRING
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.cities` (
  city_name STRING NOT NULL,
  state_code STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.us_zips` (
  zip_code STRING NOT NULL,
  city_name STRING,
  county STRING,
  state_code STRING,
  state_name STRING,
  latitude FLOAT64,
  longitude FLOAT64,
  population FLOAT64,
  median_household_income FLOAT64,
  median_age FLOAT64,
  households FLOAT64,
  income_per_capita FLOAT64,
  poverty FLOAT64,
  employed_population FLOAT64,
  unemployed_population FLOAT64,
  housing_units FLOAT64,
  source STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.brands` (
  brand_name STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.restaurants` (
  brand_name STRING NOT NULL,
  location_key STRING NOT NULL,
  name STRING NOT NULL,
  address STRING NOT NULL,
  city_name STRING NOT NULL,
  town STRING,
  state_code STRING NOT NULL,
  province STRING,
  zip_code STRING NOT NULL,
  country STRING,
  latitude FLOAT64,
  longitude FLOAT64,
  first_observed_at TIMESTAMP,
  last_observed_at TIMESTAMP
  ,franchise_name STRING
  ,concept_type STRING
  ,cuisine_type STRING
  ,neighborhood STRING
  ,district STRING
  ,phone_number STRING
  ,website_url STRING
  ,google_maps_link STRING
  ,social_media_handles STRING
  ,operating_hours STRING
  ,seating_capacity INT64
  ,service_types STRING
  ,opening_date DATE
  ,status STRING
  ,annual_revenue FLOAT64
  ,average_ticket_size FLOAT64
  ,daily_footfall INT64
  ,monthly_footfall INT64
  ,rental_cost FLOAT64
  ,lease_cost FLOAT64
  ,population_density FLOAT64
  ,average_household_income FLOAT64
  ,competitor_count INT64
  ,foot_traffic_score FLOAT64
  ,parking_availability STRING
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.mapper_configs` (
  event_id STRING NOT NULL,
  mapper_id STRING NOT NULL,
  brand_name STRING NOT NULL,
  source_name STRING NOT NULL,
  source_type STRING NOT NULL,
  field_count INT64 NOT NULL,
  config_json JSON NOT NULL,
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.indigestible_records` (
  event_id STRING NOT NULL,
  source_name STRING NOT NULL,
  row_number INT64 NOT NULL,
  errors JSON NOT NULL,
  raw_record JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.source_observations` (
  brand_name STRING NOT NULL,
  location_key STRING NOT NULL,
  source_name STRING NOT NULL,
  source_location_id STRING,
  observed_at TIMESTAMP NOT NULL,
  raw_payload JSON
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.reviews` (
  brand_name STRING NOT NULL,
  location_key STRING NOT NULL,
  review_source STRING NOT NULL,
  rating FLOAT64,
  review_count INT64,
  observed_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.analysis_runs` (
  analysis_run_id STRING NOT NULL,
  run_name STRING NOT NULL,
  subject_brand_name STRING NOT NULL,
  config_json JSON NOT NULL,
  generated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.whitespace_candidates` (
  analysis_run_id STRING NOT NULL,
  zip_code STRING NOT NULL,
  whitespace_type STRING NOT NULL,
  similarity_distance FLOAT64 NOT NULL,
  competitors_present STRING
);
