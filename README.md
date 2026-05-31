# German Job Market Analytics

A multi-source ETL pipeline that collects data engineering and analytics job
postings from four German job boards, normalises them into a common schema,
deduplicates across sources, and surfaces skill-demand trends through a
Streamlit dashboard.

---

## Why this exists

Publicly available data on which tools German employers actually require is
scattered across four major job boards with different formats, languages, and
update cadences. This project pulls all four into a single DuckDB store so
that questions like "Is Spark demand falling relative to dbt?" or "Do Berlin
roles pay more than Munich for the same title?" can be answered with a single
SQL query rather than four manual searches.

---

## Data sources

| Source | Method | ID prefix | Request gap |
|---|---|---|---|
| Bundesagentur für Arbeit | REST API v6 (official public endpoint) | `BA_` | 2 s |
| Indeed Germany | RSS feeds via feedparser | `IN_` | 3 s |
| Stepstone | HTML scraping (requests + BeautifulSoup4) | `SS_` | 10–18 s random |
| LinkedIn | Manual CSV export | `LI_` | n/a |

Keywords tracked: `Data Engineer`, `Data Analyst`, `Data Scientist`,
`Analytics Engineer`, `BI Engineer`, `Machine Learning Engineer`

Current geographic scope: Berlin (Stepstone), all major German cities via BA
and Indeed.

---

## Architecture

```
Bundesagentur API ──┐
Indeed RSS          ├──► Extract ──► Normalize ──► Deduplicate ──► Load (DuckDB) ──► Aggregate ──► Dashboard
Stepstone HTML      │
LinkedIn CSV ───────┘ (manual)
```

**Extract** — each source has its own extractor in `etl/extractors/`. Every
run saves an immutable dated snapshot under `data/raw/{source}/YYYY-MM-DD/`
before any transformation. Extractors return `[]` on failure; they never
raise.

**Normalize** — `etl/transformers/normalizer.py` maps source-specific field
names to the canonical 29-column schema (see `docs/schema.md`). It detects
description language via `langdetect`, assigns a role category from a
keyword taxonomy, and sets `employment_type` / `work_model` via regex scans.

**Enrich** — two transformer modules run after normalisation:
- `salary_parser.py` — extracts salary ranges from free text in German and
  English formats; converts monthly figures to annual.
- `skill_extractor.py` — regex word-boundary scan against ~70 canonical
  tech skills; aliases (e.g. `GCP` → `Google Cloud Platform`) collapse to a
  canonical name stored in a `VARCHAR[]` array.

**Deduplicate** — `deduplicator.py` runs two passes:
1. Within each source, repeated `job_id` values are marked.
2. Across sources, records matching on city + fuzzy company (≥ 85) + fuzzy
   title (≥ 85) + posted date (within 7 days) are collapsed; the
   higher-priority source record becomes canonical (BA > Indeed > Stepstone
   > LinkedIn).

**Load** — `duckdb_loader.py` upserts into `jobs_raw` via DELETE + INSERT
(required for `VARCHAR[]` columns in DuckDB 1.1.3). Two derived views are
maintained automatically: `jobs_clean` (non-duplicate records) and
`skills_exploded` (one row per skill per job, duplicates excluded).

**Aggregate + Dashboard** — SQL aggregations and a Streamlit app *(in
progress, Week 3)*.

---

## Tech stack

| Component | Library / tool | Version |
|---|---|---|
| Language | Python | 3.11 |
| HTTP requests | requests | 2.32.3 |
| RSS parsing | feedparser | 6.0.11 |
| HTML parsing | BeautifulSoup4 | 4.12.3 |
| Language detection | langdetect | 1.0.9 |
| Fuzzy matching | thefuzz | 0.22.1 |
| Analytical store | DuckDB | 1.1.3 |
| DataFrame layer | pandas | 2.2.2 |
| Orchestration | Apache Airflow | 2.9.3 |
| Dashboard | Streamlit | 1.36.0 |
| Charts | Plotly + Altair | 5.22.0 / 5.3.0 |
| Testing | pytest | 8.2.2 |
| Linting | black + ruff | 24.4.2 / 0.4.10 |

---

## Project structure

```
etl/
  extractors/
    bundesagentur.py   # BA API v6 — paginated fetch, dated JSON snapshot
    indeed.py          # RSS feed parser — dated CSV snapshot
    stepstone.py       # HTML scraper — slug conversion, 403/429 guard
    linkedin.py        # manual CSV reader — relative date parsing, city auto-fill
  transformers/
    normalizer.py      # canonical schema mapping, language detection, role taxonomy
    skill_extractor.py # ~70-skill regex dictionary, alias collapsing
    salary_parser.py   # German/English salary ranges, monthly → annual conversion
    deduplicator.py    # two-pass: within-source job_id + cross-source fuzzy match
  loaders/
    duckdb_loader.py   # DELETE + INSERT upsert, jobs_raw table, views

airflow/dags/
  job_market_pipeline.py  (planned — Week 3)

analytics/
  aggregations.py     (planned — Week 3)

dashboard/
  app.py              (planned — Week 3)
  charts.py           (planned — Week 3)

tests/
  extractors/         test_bundesagentur.py  test_indeed.py
                      test_stepstone.py      test_linkedin.py
  transformers/       test_normalizer.py     test_skill_extractor.py
                      test_salary_parser.py  test_deduplicator.py
  loaders/            test_duckdb_loader.py
  test_pipeline_e2e.py
  test_pipeline_integration.py   # 4-source fixture: normalize → dedup → load

docs/
  architecture.md     schema.md     decisions.md     progress.md

data/                 # gitignored — create locally before first run
  raw/                # immutable dated snapshots per source
  processed/          # optional debug intermediates
  db/                 # jobs.duckdb
```

---

## Local setup

**Prerequisites:** Python 3.11, git.

```bash
# 1. Clone and enter the repo
git clone https://github.com/adhishnanda/gjma.git
cd gjma

# 2. Create and activate the virtual environment
python3.11 -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create the data directories (gitignored, not included in the repo)
mkdir -p data/raw data/processed data/db
```

**Run the pipeline manually:**

```bash
python -m etl.extractors.bundesagentur
python -m etl.extractors.indeed
python -m etl.extractors.stepstone
# LinkedIn: place CSV files in data/raw/linkedin/YYYY-MM-DD/ before running the loader
python -m etl.loaders.duckdb_loader
```

**Format and lint:**

```bash
black . && ruff check .
```

**Start Airflow** *(once the DAG is built in Week 3)*:

```bash
airflow standalone
```

**Launch the dashboard** *(once built in Week 3)*:

```bash
streamlit run dashboard/app.py
```

---

## Running tests

```bash
pytest tests/ -v
```

The suite runs entirely offline — all HTTP calls are mocked. No live
credentials or network access required.

---

## Current status

**Week 2 complete — all 4 sources implemented and tested — 312 tests passing, 3 skipped.**

All extractors, transformers, and the loader are fully implemented. Cross-source
deduplication has been confirmed working end-to-end with all four sources through
`tests/test_pipeline_integration.py`. The pipeline is ready for Airflow
orchestration in Week 3.

| Day | Module | Status |
|---|---|---|
| 1 | Project scaffold, `.gitignore`, `requirements.txt` | Done |
| 2 | Bundesagentur extractor + tests | Done |
| 3 | Normalizer + skill extractor + tests | Done |
| 4 | Salary parser + deduplicator + tests | Done |
| 5 | DuckDB loader + views + end-to-end test | Done |
| 6 | Indeed RSS extractor + DuckDB 1.1.3 upsert fix | Done |
| 7 | Stepstone HTML scraper + tests | Done |
| 8 | LinkedIn manual CSV reader + tests | Done |
| 9 | Normalizer extended to all 4 sources; cross-source integration test | Done |

---

## Roadmap

| Day | Plan |
|---|---|
| 10 | Full pipeline dry run — real data from all 4 sources, data quality check |
| 11–12 | Apache Airflow DAG, daily schedule |
| 13–14 | Streamlit dashboard — skill trends, salary dist, role counts |
| 15 | Deploy to Streamlit Cloud |
| 16 | Full README with screenshots, architecture diagram |
| 17–18 | Final cleanup, `v1.0.0` tag |

---

## Data methodology and disclosure

This is a **research and portfolio project**. A few things worth knowing:

**Sampling, not census.** The pipeline queries a fixed set of 6 job-title
keywords across 8 German cities for Bundesagentur and Indeed, and 5
hyphenated keyword slugs in Berlin only for Stepstone. It captures a
representative but incomplete slice of the market.

**Rate limiting is built in.** Every extractor enforces minimum gaps between
requests (2 s for BA, 3 s for Indeed, 10–18 s random for Stepstone) and
stops immediately on 403 or 429 responses. The pipeline is deliberately
sequential — no parallelism.

**Source characteristics differ.** The Bundesagentur endpoint is an official
public API used by their own job-search SPA, accessed with the same API key
the app itself uses. Indeed and Stepstone are scraped from public search
pages. LinkedIn data is collected manually through LinkedIn's own CSV export
tool — no automated LinkedIn scraping.

**Raw snapshots are immutable.** `title_raw` and `description_raw` are never
modified after extraction. All transformations operate on derived fields.

**Salary data is sparse.** Most German job postings omit salary ranges.
Parsed figures come from the minority of listings that include them, so
salary distributions reflect a self-selected subset of postings.

**Not for commercial use.** All data collected is used solely for technical
analysis and demonstration purposes.

---

## Author

**Adhish Nanda**

- GitHub: [github.com/adhishnanda](https://github.com/adhishnanda)
- LinkedIn: [linkedin.com/in/adhishnanda](https://linkedin.com/in/adhishnanda)
- Email: adhish.nanda@gmail.com
