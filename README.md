# Competitive Whitespace Tool

A no-code platform for mapping your store locations against competitors, finding open markets, and keeping your location data clean — no engineering required.

## What it does

**1. Bring in your data, from any format.**
Upload a CSV, Excel, JSON, or XML file, or connect a live API — the tool reads the columns itself and suggests how they map to a standard location record (name, address, city, state, ZIP, coordinates, and more). Different brands can use completely different source formats without any re-work.

**2. AI does the tedious mapping and cleanup.**
- Auto-suggests field mappings based on column names and sample values, and learns from mappings you've confirmed before.
- Repairs common location problems automatically: ZIP codes normalized, state names corrected, swapped/inverted coordinates fixed, and offshore or clearly-wrong coordinates snapped to the nearest real city.
- Flags rows it can't confidently fix for a quick human review, with a suggested fix already attached where possible.
- Detects likely duplicate brand entries (not just similar names) and lets you merge them safely — the merge sticks even after a data reload.

**3. Nothing gets silently dropped.**
Records that fail validation are routed to a Review queue instead of vanishing. You can see exactly what's wrong, accept an AI suggestion, or fix it by hand and retry. A record fixed once won't need fixing again after a refresh.

**4. See your competitive whitespace.**
The Reporting dashboard shows your footprint next to any competitors you choose: markets covered, open ZIP codes nobody has a store in yet, state and city-level breakdowns, demographic context (population, income), and a live map. Trends over time show how coverage is changing.

**5. Track data health, not just location gaps.**
A separate Data Quality view shows how much of your data is clean vs. still being fixed, what's improving automatically vs. needs a person, and where problems are concentrated — without exposing any backend/technical detail to the user.

**6. Export what you need.**
Download your records (and competitors') as an Excel workbook, ready to share.

## Getting started

```bash
.venv/bin/python -m whitespace_tool.cli workflow-ui --host 127.0.0.1 --port 8765
```
Open http://127.0.0.1:8765/ and log in. Install `requirements.txt` first for a clean environment.

## Deploy (Render)

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `python -m whitespace_tool workflow-ui --host 0.0.0.0`

Same commands are declared in `render.yaml` (used for `render blueprint` deploys) and `Procfile`. Required environment variables (`WORKFLOW_LOGIN_USER`, `WORKFLOW_LOGIN_PASSWORD`, `BIGQUERY_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`, etc.) are listed in `render.yaml` and `.env.example`.

## More detail

Engineering handoff notes, the live bug tracker, and architecture/session history live in `internal-docs/` (gitignored — local reference only, not part of the published repo).
