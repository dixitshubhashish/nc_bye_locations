PRAGMA foreign_keys = ON;

CREATE TABLE states (
    state_id INTEGER PRIMARY KEY,
    state_code TEXT NOT NULL UNIQUE,
    state_name TEXT
);

CREATE TABLE cities (
    city_id INTEGER PRIMARY KEY,
    city_name TEXT NOT NULL,
    state_id INTEGER NOT NULL REFERENCES states(state_id),
    UNIQUE(city_name, state_id)
);

CREATE TABLE us_zips (
    zip_code TEXT PRIMARY KEY,
    city_id INTEGER REFERENCES cities(city_id),
    state_id INTEGER REFERENCES states(state_id),
    city TEXT,
    county TEXT,
    state_code TEXT,
    state_name TEXT,
    latitude REAL,
    longitude REAL,
    population REAL,
    median_household_income REAL,
    median_age REAL,
    households REAL,
    income_per_capita REAL,
    poverty REAL,
    employed_population REAL,
    unemployed_population REAL,
    housing_units REAL,
    source TEXT NOT NULL
);

CREATE TABLE brands (
    brand_id INTEGER PRIMARY KEY,
    brand_name TEXT NOT NULL UNIQUE
);

CREATE TABLE franchisees (
    franchisee_id INTEGER PRIMARY KEY,
    franchisee_name TEXT NOT NULL UNIQUE
);

CREATE TABLE restaurants (
    restaurant_id INTEGER PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(brand_id),
    location_key TEXT NOT NULL,
    name TEXT,
    address TEXT,
    city_id INTEGER REFERENCES cities(city_id),
    state_id INTEGER REFERENCES states(state_id),
    zip_code TEXT NOT NULL REFERENCES us_zips(zip_code),
    latitude REAL,
    longitude REAL,
    franchisee_id INTEGER REFERENCES franchisees(franchisee_id),
    first_observed_at TEXT,
    last_observed_at TEXT,
    UNIQUE(brand_id, location_key)
);

CREATE TABLE reviews (
    review_id INTEGER PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(restaurant_id),
    review_source TEXT NOT NULL,
    rating REAL,
    review_count INTEGER,
    observed_at TEXT NOT NULL,
    UNIQUE(restaurant_id, review_source, observed_at)
);

CREATE TABLE source_observations (
    observation_id INTEGER PRIMARY KEY,
    restaurant_id INTEGER REFERENCES restaurants(restaurant_id),
    source_name TEXT NOT NULL,
    source_location_id TEXT,
    observed_at TEXT NOT NULL,
    raw_payload TEXT,
    UNIQUE(source_name, source_location_id, observed_at)
);

CREATE TABLE analysis_runs (
    analysis_run_id INTEGER PRIMARY KEY,
    run_name TEXT NOT NULL,
    subject_brand_id INTEGER NOT NULL REFERENCES brands(brand_id),
    config_json TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE TABLE whitespace_candidates (
    candidate_id INTEGER PRIMARY KEY,
    analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(analysis_run_id),
    zip_code TEXT NOT NULL REFERENCES us_zips(zip_code),
    whitespace_type TEXT NOT NULL,
    similarity_distance REAL NOT NULL,
    competitors_present TEXT,
    UNIQUE(analysis_run_id, zip_code)
);
