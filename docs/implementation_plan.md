# Implementation Plan: Competitive Whitespace Data Platform

## Overview
The tool ingests messy brand/location sources, maps them into a shared location model, validates and enriches them, sends invalid rows to review, and powers competitive whitespace reporting. The current architecture uses BigQuery as the authoritative warehouse and persistent SQLite mirrors for fast local reads, startup readiness, reporting payloads, review counters, ZIP/worldwide-city lookups, and background repair state.

---

## Architecture & Data Flow

```
┌────────────────────────────────────────┐
│  Source Adapters / Demo Sources        │
│  CSV, Excel, JSON, XML, GET API, Python│
└──────────────────┬─────────────────────┘
                   │
                   ▼ [Parse <= 50 for mapping, save full source]
┌────────────────────────────────────────────────────────┐
│  Shared Warehouse Tables                               │
│  businesses, source_types, workflow_templates, listings│
│  error_listings, us_zipcodes, quality_fix_events       │
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼ [Validation, enrichment, mirrors, reporting]
┌────────────────────────────────────────────────────────┐
│  Reporting + Review                                    │
│  valid/enriched listings, invalid review rows, gaps,   │
│  quality metrics, background automatic repair          │
└────────────────────────────────────────────────────────┘
```

---

## Implemented Components

### 1. Source Mapping Workflow
- Source-specific parsing lives under `whitespace_tool/source_adapters`.
- The mapper previews a small sample for field detection and mapping UX, then save reloads and processes the full source.
- Required fields are always visible and ordered first. Optional fields can be auto-detected or manually added to the mapping.
- Brands and source formats are independent; a brand can use different formats over its lifetime.

---

### 2. Validation & Fuzzy Enrichment
- Mandatory validation checks brand/business, location name, address, city, state, ZIP, and country.
- Invalid rows go to Review Error Listings instead of blocking good rows.
- `whitespace_tool/geo_enrichment.py` normalizes city/state/country text, detects inverted latitude/longitude, realigns ZIPs from city/state when appropriate, and uses nearest cached city/ZIP/worldwide city for coordinate repair.
- Automatic review repair is intentionally lightweight. It works from a persisted SQLite queue, claims a tiny batch, records AI/manual fix events, and updates review/reporting counters.

---

### 3. Reporting
- Location Intelligence & Whitespace tab: primary/competitor brands, geography filters, demographics filters, active location KPIs, state/city distributions, ZIP gaps, sample records, and Leaflet map markers.
- Data Quality & Improvements tab: invalid listings, manual review queue, automatic/manual fixes, unresolved rate, issue categories, impacted brands, impacted states/cities, and reconciliation notes.
- Data Quality also reports ZIP and coordinate completeness, duplicate rate, stale records, entity-resolution attempts/success, durable daily snapshot history, and period comparisons.
- Reporting reads SQLite mirrors first where possible, then falls back to live warehouse queries and refreshes mirrors silently.

---

## Assessment Coverage

| Requirement | Current coverage | Remaining gap |
| --- | --- | --- |
| Change brands without rewrite | Brand registry, templates, mapper, reporting filters | Demo metadata needs occasional reconciliation with UI demos |
| Change geography | State/county/city/ZIP filters and config geography | Metro-area abstraction is not first-class yet |
| Change metrics | `config/demo.json` controls similarity metrics | Run-over-run metric snapshots not built |
| Separate source-specific logic | Source adapters and workflow templates | `workflow_server.py` still centralizes too many orchestration concerns |
| Visible upstream/source failures | Parse errors, review table, quality tab, dismissible warnings | Browser smoke coverage should prove all states |
| Provenance/observed timestamps | Content hashes, source metadata, observed timestamps | No historical diff/snapshot table yet |
| Larger-volume behavior | 50-row parse sample, full-source save, mirrors, background repair | Need sustained load test beyond unit coverage |

## Current Risk Register

- `workflow_server.py` is still the main coupling point and should be split after the current stabilization window.
- Mapping label drift exists: listing `name` is currently labeled `Brand Name` in mapper config, while brand/business is a separate object.
- The active Python schema is ahead of older SQL files, so generated schemas should be treated as authoritative until SQL artifacts are regenerated.
- Quality reporting combines current active invalid rows with persisted fix counters; reconciliation must be watched whenever rows are soft-deleted from review.
- Authenticated browser smoke testing should be the next confidence step before calling the app stable.
