# Pipeline Architecture

## Overview

Three active sources feed a sequential ETL pipeline that lands data in DuckDB
and surfaces it through a Streamlit dashboard. Airflow schedules the daily run;
LinkedIn is manual-only.

```
Bundesagentur API ──┐
Stepstone HTML      ├──► Extract ──► Normalise ──► Deduplicate ──► Load ──► Aggregate ──► Dashboard
LinkedIn CSV ───────┘ (manual)                                    DuckDB     (SQL)       (Streamlit)

Indeed RSS          ✗  blocked (HTTP 403) — extractor retained, no live data
```

---

## Detailed data flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  EXTRACT  (etl/extractors/)                                                  │
│                                                                              │
│  Bundesagentur API ──► bundesagentur.py ──► raw/bundesagentur/YYYY-MM-DD/   │
│                         REST API v6                jobs.json                 │
│                         6 keywords × 8 cities                               │
│                                                                              │
│  Stepstone HTML ────► stepstone.py ─────► raw/stepstone/YYYY-MM-DD/         │
│                         requests + BS4        stepstone.json                 │
│                         5 slugs × Berlin                                     │
│                                                                              │
│  LinkedIn CSV ──────► linkedin.py ──────► raw/linkedin/YYYY-MM-DD/          │
│                         manual export         *.csv  (manual placement)      │
│                                                                              │
│  Indeed RSS ────────► indeed.py ────────► []  (HTTP 403 — all feeds)        │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ list[dict] per source
┌──────────────────────────────────────────────────────────────────────────────┐
│  TRANSFORM  (etl/transformers/)                                              │
│                                                                              │
│  normalizer.py       maps source fields → 29-column canonical schema        │
│                      detects language (langdetect)                           │
│                      assigns role_category from keyword taxonomy             │
│                      sets work_model / employment_type via regex             │
│                                                                              │
│  skill_extractor.py  regex word-boundary scan of description_raw            │
│                      ~70 canonical skills, alias collapsing                  │
│                      fills skills VARCHAR[]                                  │
│                                                                              │
│  salary_parser.py    extracts salary ranges from free text                  │
│                      German + English formats, monthly → annual              │
│                      fills salary_min / salary_max / currency                │
│                                                                              │
│  deduplicator.py     Pass 1 — within-source: mark repeated job_id           │
│                      Pass 2 — cross-source: city + fuzzy company (≥85)      │
│                               + fuzzy title (≥85) + date within 7 days      │
│                               priority: BA=0 > Indeed=1 > SS=2 > LI=3      │
│                      sets is_duplicate BOOLEAN, canonical_id VARCHAR         │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ deduplicated list[dict]
┌──────────────────────────────────────────────────────────────────────────────┐
│  LOAD  (etl/loaders/)                                                        │
│                                                                              │
│  duckdb_loader.py    DELETE + INSERT upsert (no INSERT OR REPLACE —         │
│                      fails on VARCHAR[] in DuckDB 1.1.3)                    │
│                      drop_duplicates(subset="job_id") before staging        │
│                                                                              │
│  data/db/jobs.duckdb                                                         │
│  ├── jobs_raw          PRIMARY KEY job_id, all records including duplicates  │
│  ├── jobs_clean        VIEW — WHERE is_duplicate = FALSE                     │
│  └── skills_exploded   VIEW — UNNEST(skills), is_duplicate = FALSE          │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ DuckDB connection (read-only)
┌──────────────────────────────────────────────────────────────────────────────┐
│  AGGREGATE  (analytics/)                                                     │
│                                                                              │
│  aggregations.py     five functions, each accepts an open connection,       │
│                      returns a pd.DataFrame                                  │
│                                                                              │
│  skill_demand_weekly  skill × week_start × count  (via skills_exploded)     │
│  role_by_city         role_category × city × count                          │
│  salary_dist          role_category × salary_min/max  (non-null only)       │
│  language_ratio       source × language × pct                               │
│  source_coverage      source × snapshot_date × count                        │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  DASHBOARD  (dashboard/)                                                     │
│                                                                              │
│  app.py     @st.cache_resource DuckDB connection (one per server process)   │
│             sidebar filters: date range, city, role category                 │
│             Python-level filtering on returned DataFrames                    │
│                                                                              │
│  charts.py  Plotly graph_objects throughout (Altair not used)               │
│             skill_trend_chart  role_by_city_chart  role_donut_chart         │
│             source_coverage_chart  language_ratio_chart                      │
│                                                                              │
│  Live: https://german-job-market-analytics.streamlit.app                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Source characteristics

| Source | Method | ID prefix | Sleep between requests | Schedule |
|---|---|---|---|---|
| Bundesagentur für Arbeit | REST API (v6) | `BA_` | 2 s | Daily (Airflow) |
| Stepstone | HTML scraping | `SS_` | 10–18 s random | Daily (Airflow) |
| LinkedIn | Manual CSV export | `LI_` | n/a | Manual trigger |
| Indeed Germany | RSS feed — **blocked (HTTP 403)** | `IN_` | 3 s | — |

---

## Stage 1 — Extract

Each extractor lives in `etl/extractors/{source}.py` and follows the same
contract:

- Iterates over `KEYWORDS × CITIES` combinations.
- Saves an immutable dated snapshot **before** any transformation:
  `data/raw/{source}/YYYY-MM-DD/{file}`.
- Returns a flat `list[dict]` of raw records; returns `[]` on failure, never raises.
- `title_raw` and `description_raw` are never modified after extraction.

### Bundesagentur (`BA_`)
- Endpoint: `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs`
- Auth: `X-API-Key: jobboerse-jobsuche` header (no OAuth required)
- Requires a browser-like `User-Agent`; Python default fails WAF check
- Pagination: 1-indexed `page` param; total count in `maxErgebnisse`; records in `ergebnisliste`
- Unique ID: `referenznummer` → stored as `BA_{referenznummer}`
- Returns structured `employment_type` and `work_model` fields — no regex needed
- Returns `lat`/`lon`/`postal_code`/`region` — no other source does

### Stepstone (`SS_`)
- HTML scraping with `requests` + `BeautifulSoup4` (not Playwright or requests-html)
- 5 keyword slugs × Berlin only; max 2 pages per slug (configurable)
- Random sleep `random.uniform(10, 18)` between every page request
- On 403/429: stop remaining locations for that keyword, continue next keyword
- Search-result cards contain no `description_raw` — field is always `""`

### LinkedIn (`LI_`)
- Manual export: save search results as CSV from LinkedIn's own export tool
- CSV template at `docs/linkedin_manual_template.csv`
- `etl/extractors/linkedin.py` is a CSV reader, not a scraper
- `posted_at_raw` is a relative timestamp ("N days ago") converted to ISO ±2 days
- `city_raw` defaults to `"Berlin"` when blank (collection scoped to Berlin)
- `is_remote=True` covers both remote and hybrid — LinkedIn does not distinguish

### Indeed (`IN_`)
- All `de.indeed.com/rss` feeds return HTTP 403 as of the first live run (2026-05-31)
- Extractor returns `[]` gracefully; code and fixture-based tests are retained
- `IN_` prefix and deduplicator priority slot (index 1) kept in place
- Not an active data source; see `docs/decisions.md` for the final decision rationale

---

## Stage 2 — Transform

Three transformers are applied in sequence per source batch.

### Normalizer (`etl/transformers/normalizer.py`)
Maps source-specific field names to the 29-column canonical schema (see
`docs/schema.md`). Dispatches to a per-source normalizer function
(`_normalize_bundesagentur`, `_normalize_stepstone`, `_normalize_linkedin`,
`_normalize_indeed`). Shared logic:

- Language detection via `langdetect`; returns `"unknown"` on failure (short or
  empty descriptions fail detection)
- Role taxonomy match via ordered `list[tuple]`; first match wins; falls through
  to `"Other"` when nothing matches
- `work_model` and `employment_type` default to `"UNKNOWN"` (not `None`)
- `_parse_posted_date` handles ISO, ISO 8601 with time, DD-MM-YYYY, and RFC 2822

### Skill extractor (`etl/transformers/skill_extractor.py`)
Regex word-boundary scan (`\b`, case-insensitive) over `description_raw`.
~70 canonical skills; aliases collapse to a canonical name. Returns a
deduplicated `list[str]` in dictionary iteration order (stable, no sort needed).
Coverage is bounded by the fraction of records that have a non-empty
`description_raw` — currently near-zero for BA and Stepstone.

### Salary parser (`etl/transformers/salary_parser.py`)
Extracts salary ranges from free text. Handles `€60.000/Jahr`,
`4.500 € mtl.`, and English equivalents. Converts monthly figures to annual.
When only a single figure is found, both `salary_min` and `salary_max` are set
to that value.

---

## Stage 3 — Deduplicate

`etl/transformers/deduplicator.py` operates on the merged output of all sources.

**Pass 1 — within-source job_id dedup**
Within each source, records sharing the same `job_id` are marked. The first
occurrence is canonical; subsequent occurrences have `is_duplicate=True`.
BA returns the same `referenznummer` across multiple keyword × city queries;
this pass collapses them.

**Pass 2 — cross-source fuzzy match**
Records surviving Pass 1 are sorted by source priority
(BA=0, Indeed=1, Stepstone=2, LinkedIn=3). The highest-priority record for each
matched cluster becomes canonical. Match criteria:

- Same `city` (hard requirement — skipped if either record has `city=None`)
- Same `posted_date` within 7 days (hard requirement — skipped if either is `None`)
- `fuzz.ratio(company_a, company_b) >= 85`
- `fuzz.ratio(title_normalized_a, title_normalized_b) >= 85`

Fields set by the deduplicator:

| Field | Type | Meaning |
|---|---|---|
| `is_duplicate` | BOOLEAN | `TRUE` if a higher-priority canonical record covers this posting |
| `canonical_id` | VARCHAR | `job_id` of the canonical record; `NULL` if this record is canonical |

---

## Stage 4 — Load

`etl/loaders/duckdb_loader.py` upserts into `data/db/jobs.duckdb`.

Upsert strategy: DELETE + INSERT per statement, no explicit `BEGIN/COMMIT`
(wrapping in a transaction breaks `_staging` view visibility in DuckDB 1.1.3).
Before staging, records are sorted by `is_duplicate` ascending and
`drop_duplicates(subset="job_id", keep="first")` applied — this ensures BA's
repeated `referenznummer` across keyword × city combos resolves to the canonical
version before hitting the `PRIMARY KEY` constraint.

### Table: `jobs_raw`
All records ever fetched, including duplicates. `job_id` is the primary key.
Full column list in `docs/schema.md`.

### View: `jobs_clean`
```sql
CREATE VIEW jobs_clean AS
SELECT * FROM jobs_raw WHERE is_duplicate = FALSE;
```

### View: `skills_exploded`
```sql
CREATE VIEW skills_exploded AS
SELECT job_id, source, posted_date, UNNEST(skills) AS skill
FROM jobs_raw WHERE is_duplicate = FALSE;
```

---

## Stage 5 — Aggregate

`analytics/aggregations.py` exposes five functions. Each accepts an open
`duckdb.DuckDBPyConnection` and returns a `pd.DataFrame`. All query `jobs_clean`
or `skills_exploded` (never `jobs_raw` directly).

| Function | Source view | Returns |
|---|---|---|
| `skill_demand_weekly` | `skills_exploded` | skill, week_start, count |
| `role_by_city` | `jobs_clean` | role_category, city, count |
| `salary_dist` | `jobs_clean` | role_category, salary_min, salary_max (non-null only) |
| `language_ratio` | `jobs_clean` | source, language, count, pct |
| `source_coverage` | `jobs_clean` | source, snapshot_date, count |

---

## Stage 6 — Dashboard

`dashboard/app.py` opens a single read-only DuckDB connection via
`@st.cache_resource` (one per server process lifetime). Sidebar filters are
applied in Python on the returned DataFrames — the aggregation DataFrames are
small enough that Python filtering costs microseconds and avoids parameterising
the SQL queries.

| Chart | Aggregation function |
|---|---|
| Skill demand over time | `skill_demand_weekly` |
| Role count by city (bar) | `role_by_city` |
| Role breakdown (donut) | `role_by_city` (city dimension collapsed) |
| Source coverage | `source_coverage` |
| Language ratio | `language_ratio` |

Note: a salary distribution chart was not added. Salary coverage is ~5–10% of
canonical records; a histogram or box plot at that volume would be misleading.
The `salary_dist` aggregation is ready; the chart will be added once detail-page
fetching increases salary coverage.

---

## Airflow DAG (`airflow/dags/job_market_pipeline.py`)

DAG ID: `job_market_pipeline` | Schedule: `@daily` | Catchup: `false`

```
extract_ba ──► normalize_ba ──┐
extract_ss ──► normalize_ss ──┼──► deduplicate_all ──► load_to_duckdb
load_li    ──► normalize_li ──┘
```

Three active extract tasks (BA, Stepstone, LinkedIn); the three extract/normalise
pairs run in parallel. `deduplicate_all` depends on all three. `load_to_duckdb`
runs after deduplication.

LinkedIn uses a `FileSensor` watching `data/raw/linkedin/{{ ds }}/` rather than
a time trigger. `start_date` uses `pendulum.now("UTC").subtract(days=1)`
(Airflow 3.x; `days_ago` was removed in 3.0). Schedule accessed via `dag.schedule`
(not `dag.schedule_interval`, which was also removed in 3.0).

---

## File layout

```
data/
  raw/
    bundesagentur/YYYY-MM-DD/jobs.json        # immutable snapshots
    stepstone/YYYY-MM-DD/stepstone.json
    indeed/YYYY-MM-DD/indeed_rss.csv          # retained, no live data
    linkedin/YYYY-MM-DD/*.csv                 # manually placed
  processed/                                  # optional debug intermediates
  db/
    jobs.duckdb                               # analytical store (committed for Streamlit Cloud)

etl/
  extractors/    bundesagentur.py  stepstone.py  linkedin.py  indeed.py
  transformers/  normalizer.py  skill_extractor.py  salary_parser.py  deduplicator.py
  loaders/       duckdb_loader.py
  pipeline_runner.py   # orchestrates all 4 stages + summary report
  data_quality.py      # 5-check post-load quality report

airflow/dags/    job_market_pipeline.py
analytics/       aggregations.py
dashboard/       app.py  charts.py
tests/           (mirrors etl/ structure; 312 passing, 3 skipped)
docs/            architecture.md  schema.md  decisions.md  progress.md
```

`data/raw/` and `data/processed/` are gitignored. `data/db/jobs.duckdb` is
committed (2.26 MB) so Streamlit Cloud can access it without a pipeline run.

---

## Data quality

`etl/data_quality.py` runs five checks after each pipeline load and prints a
pass/fail report. Thresholds are constants at the top of the module.

| Check | Threshold | Typical result |
|---|---|---|
| Source distribution — all expected sources present | — | FAIL (Indeed permanently missing) |
| Null rate per field | < 20% | OK for most fields; Stepstone `posted_date` ~8% null |
| Date range — no posts older than N days | 90 days | FAIL (BA includes historical active records from 2025) |
| Duplicate rate | < 30% | OK |
| Skill coverage — fraction of canonical records with ≥1 skill | > 50% | FAIL (~3.5%) |

Three of the five checks produce expected, permanent failures. They are not bugs;
the thresholds reflect aspirational targets that require future work (detail-page
fetching) or cannot be met structurally (Indeed blocked).

### Coverage gaps and disclosure

**Skill coverage (~3.5%)**
BA search-list records and Stepstone search-result cards include title and
metadata only — no `description_raw` text. `skill_extractor` operates on
`description_raw`, so skill extraction is near-zero for both sources. Of the 541
canonical records from the Day 10 live run, only 19 had at least one skill
detected. Skill signal currently comes entirely from LinkedIn.

The path to meaningful skill coverage is fetching individual job detail pages
for BA and Stepstone. This was deferred because it requires significantly more
HTTP requests, rate-limit handling, and HTML parsing surface area. The schema
already accommodates the data; no field changes are needed.

**Salary data (~5–10% coverage)**
Most German job postings do not state salary ranges. Parsed figures come from
the minority that do, so `salary_dist` reflects a self-selected subset and
should not be treated as a market-wide estimate. Salary coverage does not
improve with detail-page fetching — it depends on employer disclosure practice.

**Indeed (0% coverage)**
All five `de.indeed.com/rss` feeds return HTTP 403 on every run. Indeed is not
an active source. The extractor code is retained for re-enablement if a
compliant access path becomes available. The `IN_` job-ID prefix and
deduplicator priority slot are left in place to avoid disrupting cross-source
dedup logic.

**LinkedIn freshness**
LinkedIn data is collected manually and is only as fresh as the last export.
It is not refreshed on the Airflow daily schedule. The `FileSensor` in the DAG
waits for a CSV file at `data/raw/linkedin/{{ ds }}/`; if none is present the
sensor times out and the LinkedIn normalise task is skipped for that day.

**Geographic scope**
Stepstone and LinkedIn data covers Berlin only. Bundesagentur covers 8 major
German cities (Berlin, Munich, Hamburg, Frankfurt, Cologne, Stuttgart,
Düsseldorf, Leipzig). The pipeline does not cover smaller cities or rural
markets.

**Sampling, not census**
The pipeline queries a fixed set of 6 job-title keywords. It captures a
representative but incomplete slice of the market. Niche roles (e.g. "Data
Platform Engineer", "Analytics Translator") that do not match the keyword list
are not collected.
