# Pipeline Architecture

## Overview

Four sources feed a sequential ETL pipeline that lands data in DuckDB and
surfaces it through a Streamlit dashboard. Airflow schedules the daily run;
LinkedIn is manual-only.

```
Bundesagentur API ──┐
Indeed RSS          ├──► Extract ──► Normalize ──► Deduplicate ──► Load ──► Aggregate ──► Dashboard
Stepstone HTML      │                                              DuckDB   (SQL)          (Streamlit)
LinkedIn CSV ───────┘  (manual)
```

---

## Source characteristics

| Source | Method | ID prefix | Sleep between requests | Schedule |
|---|---|---|---|---|
| Bundesagentur für Arbeit | REST API (v6) | `BA_` | 2 s | Daily |
| Indeed Germany | RSS feed | `IN_` | 3 s | Daily |
| Stepstone | HTML scraping | `SS_` | 10–18 s random | Daily |
| LinkedIn | Manual CSV export | `LI_` | n/a | Manual trigger |

---

## Stage 1 — Extract

Each extractor lives in `etl/extractors/{source}.py` and follows the same
contract:

- Iterates over `KEYWORDS × CITIES` combinations.
- Saves a dated raw snapshot **before** any transformation:
  `data/raw/{source}/YYYY-MM-DD/{file}`.
- Returns a flat `list[dict]` of raw records; returns `[]` on failure, never
  raises.
- Raw snapshots are immutable — `title_raw` and `description_raw` are never
  modified after extraction.

### Bundesagentur (`BA_`)
- Endpoint: `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs`
- Auth: `X-API-Key: jobboerse-jobsuche` header (no OAuth required for public search)
- Pagination: 1-indexed `page` param; reads `maxErgebnisse` from the response to
  determine total pages; list is under the `ergebnisliste` key
- Unique ID: `referenznummer` field

### Indeed (`IN_`)
- Consumes the Indeed Germany RSS feed via `feedparser`
- One feed URL per keyword/city combination
- No session or cookie management required

### Stepstone (`SS_`)
- HTML scraping with `requests` + `BeautifulSoup4` (no Playwright or
  requests-html — both get blocked faster)
- Random sleep `random.uniform(10, 18)` between every page request
- Tested on 1 keyword × 1 page initially; expanded once rate-limit behaviour
  is confirmed

### LinkedIn (`LI_`)
- Manual export: save search results as CSV from LinkedIn's own export
- CSV template lives at `docs/linkedin_manual_template.csv`
- `etl/extractors/linkedin.py` is a CSV reader, not a scraper

---

## Stage 2 — Transform

Three transformers are applied in sequence per source batch.

### Normalizer (`etl/transformers/normalizer.py`)
Maps source-specific field names to the canonical schema defined in
`docs/schema.md`. Adds `source`, `fetched_at`, `snapshot_date`,
`title_normalized`, `work_model`, `employment_type`, and `language`
(detected via `langdetect`). Calls `salary_parser` and `skill_extractor`
as sub-steps and attaches their results to the record.

### Skill extractor (`etl/transformers/skill_extractor.py`)
Regex/keyword scan over `description_raw`. Returns a deduplicated
`list[str]` of recognised tech skills. Skill dictionary is organised by
category; see the Skills section in `docs/schema.md` for the full list.

### Salary parser (`etl/transformers/salary_parser.py`)
Extracts salary ranges from free text in `description_raw` and `salary_raw`.
Returns `{'min': float|None, 'max': float|None, 'currency': str|None}`.
Handles both annual (`€60.000/Jahr`) and monthly (`4.500 € mtl.`) formats
and converts monthly figures to annual.

---

## Stage 3 — Deduplicate

`etl/transformers/deduplicator.py` runs across the merged output of all four
sources after normalisation. Two-pass logic:

1. **Exact key match** — records sharing the same `title_normalized + company + city + posted_date`
   hash are duplicates; the later-fetched copy is marked.
2. **Description similarity** — TF-IDF cosine similarity above 0.92 flags
   near-duplicate descriptions that slipped through the key match (common
   for Stepstone reposts of BA listings).

Fields set by the deduplicator:

| Field | Type | Description |
|---|---|---|
| `is_duplicate` | BOOLEAN | `true` if a canonical record exists for this posting |
| `canonical_id` | VARCHAR | `job_id` of the canonical record; `null` if this record is canonical |

---

## Stage 4 — Load

`etl/loaders/duckdb_loader.py` upserts normalised records into
`data/db/gjma.duckdb`.

### Table: `jobs_raw`
Stores every record ever fetched, including duplicates. Upsert key is
`job_id`. Full column list in `docs/schema.md`.

### View: `jobs_clean`
Filters `jobs_raw` to non-duplicate, non-null records:

```sql
CREATE VIEW jobs_clean AS
SELECT *
FROM jobs_raw
WHERE is_duplicate = false
  AND title_raw IS NOT NULL;
```

---

## Stage 5 — Aggregate

`analytics/aggregations.py` runs pre-defined SQL queries against `jobs_clean`
and materialises summary tables in DuckDB:

- Skill demand counts by week
- Role category counts by city
- Salary distribution by role category
- English vs German posting ratio by source
- Source coverage (posting count per source per day)

---

## Stage 6 — Dashboard

`dashboard/app.py` (Streamlit) reads directly from `data/db/gjma.duckdb`
via DuckDB's Python client. Charts are defined in `dashboard/charts.py`.

| Chart | Data |
|---|---|
| Skill demand over time | `skill_demand_weekly` |
| Role count by city | `role_by_city` |
| Salary distribution by role | `salary_dist` |
| Source coverage comparison | `source_coverage` |
| English vs German ratio | `language_ratio` |

Sidebar filters: date range, city, role category.

---

## Airflow DAG (`airflow/dags/job_market_pipeline.py`)

DAG ID: `job_market_pipeline` | Schedule: `@daily` | Catchup: `false`

```
extract_bundesagentur ──► normalize_bundesagentur ──┐
extract_indeed        ──► normalize_indeed        ──┤
extract_stepstone     ──► normalize_stepstone     ──┼──► deduplicate_all ──► load_to_duckdb ──► aggregate
load_linkedin_csv     ──► normalize_linkedin      ──┘
```

The four extract/normalize pairs run in parallel (no interdependency).
`deduplicate_all` has all four normalize tasks as upstream dependencies.
`load_to_duckdb` and `aggregate` run sequentially after deduplication.
LinkedIn uses a file-sensor task that watches `data/raw/linkedin/` rather
than a time trigger.

---

## File layout

```
data/
  raw/
    bundesagentur/YYYY-MM-DD/jobs.json        # immutable snapshots
    indeed/YYYY-MM-DD/{keyword}_{city}.json
    stepstone/YYYY-MM-DD/{keyword}_{city}.json
    linkedin/YYYY-MM-DD/export.csv
  processed/                                  # optional debug intermediates
  db/
    gjma.duckdb                               # analytical store

etl/
  extractors/    bundesagentur.py  indeed.py  stepstone.py  linkedin.py
  transformers/  normalizer.py  skill_extractor.py  salary_parser.py  deduplicator.py
  loaders/       duckdb_loader.py

airflow/dags/    job_market_pipeline.py
analytics/       aggregations.py
dashboard/       app.py  charts.py
tests/           (mirrors etl/ structure)
docs/            architecture.md  schema.md  decisions.md  progress.md
```

All `data/` contents are gitignored. Fresh-clone setup: `mkdir -p data/{raw,processed,db}`.
