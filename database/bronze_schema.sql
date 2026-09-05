CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.field_catalogs` (
  field_id STRING NOT NULL DEFAULT GENERATE_UUID(),
  business_id STRING,
  slug STRING NOT NULL,
  label STRING NOT NULL,
  table_name STRING NOT NULL,
  field_name STRING NOT NULL,
  data_type STRING NOT NULL,
  required BOOL NOT NULL,
  hints JSON NOT NULL,
  aliases JSON NOT NULL,
  is_custom BOOL NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.us_zipcodes` (
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

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.businesses` (
  business_id STRING NOT NULL DEFAULT GENERATE_UUID(),
  name STRING NOT NULL,
  slug STRING NOT NULL,
  source_type_id STRING,
  description STRING,
  logo_url STRING,
  website_url STRING,
  status STRING NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  meta_title STRING,
  meta_description STRING,
  country_of_origin STRING,
  is_sample_data BOOL DEFAULT FALSE,
  sample_batch_id STRING,
  is_deleted BOOL DEFAULT FALSE,
  deleted_on TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.listings` (
  listing_id STRING NOT NULL DEFAULT GENERATE_UUID(),
  business_id STRING NOT NULL,
  source_type_id STRING NOT NULL,
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
  ,template_id STRING
  ,ingestion_id STRING
  ,mapping_id STRING
  ,validation_status STRING
  ,is_sample_data BOOL DEFAULT FALSE
  ,sample_batch_id STRING
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
  ,parking_availability STRING,
  is_deleted BOOL DEFAULT FALSE,
  deleted_on TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.workflow_templates` (
  workflow_template_id STRING NOT NULL DEFAULT GENERATE_UUID(),
  business_id STRING NOT NULL,
  source_type_id STRING,
  name STRING NOT NULL,
  components JSON NOT NULL,
  archived_components JSON,
  source_configuration JSON,
  is_sample_data BOOL DEFAULT FALSE,
  sample_batch_id STRING,
  is_deleted BOOL DEFAULT FALSE,
  deleted_on TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.source_types` (
  source_type_id STRING NOT NULL DEFAULT GENERATE_UUID(),
  name STRING NOT NULL,
  data_format JSON NOT NULL,
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.error_listings` (
  event_id STRING NOT NULL,
  business_id STRING NOT NULL,
  source_type_id STRING NOT NULL,
  row_number INT64 NOT NULL,
  errors JSON NOT NULL,
  raw_record JSON NOT NULL,
  observed_at TIMESTAMP NOT NULL,
  template_id STRING,
  ingestion_id STRING,
  mapping_id STRING,
  validation_error_type STRING,
  country STRING,
  is_sample_data BOOL DEFAULT FALSE,
  sample_batch_id STRING,
  is_deleted BOOL DEFAULT FALSE,
  deleted_on TIMESTAMP
);
