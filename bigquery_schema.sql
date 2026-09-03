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
  name STRING,
  address STRING,
  city_name STRING,
  state_code STRING,
  zip_code STRING NOT NULL,
  latitude FLOAT64,
  longitude FLOAT64,
  first_observed_at TIMESTAMP,
  last_observed_at TIMESTAMP
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
