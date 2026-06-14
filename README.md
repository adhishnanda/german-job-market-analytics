# German Job Market Analytics

> Multi-source ETL pipeline tracking skill demand across German data and analytics job postings - with a live Streamlit dashboard.

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square)
![DuckDB](https://img.shields.io/badge/DuckDB-1.1.3-yellow?style=flat-square)
![Airflow](https://img.shields.io/badge/Airflow-3.2.2-017CEE?style=flat-square)
![Streamlit](https://img.shields.io/badge/Streamlit-1.36.0-FF4B4B?style=flat-square)
![Tests](https://img.shields.io/badge/tests-347%20passing-brightgreen?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)

**[→ Live Dashboard](https://german-job-market-analytics.streamlit.app)** &nbsp;·&nbsp; **[→ Portfolio](https://adhishnanda.github.io)**

---

## Research question

Which tools do German employers actually require for data and analytics roles, and how is demand shifting over time?

---

## Key findings

From 574 canonical records across 8 German cities:

| Skill | Postings |
|---|---|
| SQL | 18 |
| Python | 13 |
| Tableau | 7 |
| Looker | 6 |
| dbt | 5 |

Top hiring companies: Tesla Germany (37 postings), Akkodis (16), Mercedes-Benz (16).

Deduplication rate: ~41% — the same posting appears across multiple sources and keyword queries.

---

## Architecture

![Pipeline Architecture](docs/diagrams/architecture.svg)

```
Bundesagentur API  ──┐
Stepstone scraper  ──┼──► Normalise ──► Enrich ──► Deduplicate ──► DuckDB ──► Streamlit
LinkedIn CSV       ──┘
Indeed RSS         ✗  blocked (HTTP 403)
```

Six stages:

1. **Extract** - each source has its own extractor in `etl/extractors/`. Every run saves an immutable dated snapshot under `data/raw/{source}/YYYY-MM-DD/`. Extractors return `[]` on failure and never raise.
2. **Normalise** - `normalizer.py` maps source fields to a canonical 29-column schema, detects description language via `langdetect`, and assigns a role category from a keyword taxonomy.
3. **Enrich** - `salary_parser.py` extracts salary ranges from free text (German and English formats). `skill_extractor.py` runs regex word-boundary matching against ~70 canonical skills with alias collapsing.
4. **Deduplicate** — two-pass: within-source repeated `job_id` values, then cross-source fuzzy matching on city + company + title + date. Priority order: BA > Indeed > Stepstone > LinkedIn.
5. **Load** - `duckdb_loader.py` upserts via DELETE + INSERT into `jobs_raw`. Two views are maintained: `jobs_clean` (non-duplicates) and `skills_exploded` (one row per skill per job).
6. **Aggregate and display** — five SQL aggregation functions in `analytics/aggregations.py` feed the Streamlit dashboard. Refreshed daily via GitHub Actions.

Full schema: [`docs/schema.md`](docs/schema.md) · Architecture decisions: [`docs/decisions.md`](docs/decisions.md)

---

## Data sources

| Source | Method | ID prefix | Request gap | Status |
|---|---|---|---|---|
| Bundesagentur für Arbeit | REST API v6 (official) | `BA_` | 2 s | Active |
| Stepstone | HTML scraping (requests + BS4) | `SS_` | 10-18 s random | Active |
| LinkedIn | Manual CSV export | `LI_` | n/a | Active (manual) |
| Indeed Germany | RSS feed | `IN_` | 3 s | Blocked (HTTP 403) |

Keywords: `Data Engineer`, `Data Analyst`, `Data Scientist`, `Analytics Engineer`, `BI Engineer`, `Machine Learning Engineer`

Geographic scope: Berlin (Stepstone and LinkedIn), 8 major German cities (Bundesagentur).

---

## Tech stack

| Component | Tool | Version |
|---|---|---|
| Language | Python | 3.11 |
| Analytical store | DuckDB | 1.1.3 |
| Orchestration | Apache Airflow | 3.2.2 |
| Dashboard | Streamlit | 1.36.0 |
| Charts | Plotly | 5.22.0 |
| HTTP requests | requests | 2.32.3 |
| HTML parsing | BeautifulSoup4 | 4.12.3 |
| Fuzzy matching | thefuzz | 0.22.1 |
| Language detection | langdetect | 1.0.9 |
| DataFrames | pandas | 2.2.2 |
| Testing | pytest | 8.2.2 |
| Linting | black + ruff | 24.4.2 / 0.4.10 |
| CI | GitHub Actions | - |

---

## Project structure

```
german-job-market-analytics/
├── etl/
│   ├── extractors/
│   │   ├── bundesagentur.py     # BA API v6 — paginated fetch, dated JSON snapshot
│   │   ├── stepstone.py         # HTML scraper — 403/429 guard, random sleep
│   │   ├── linkedin.py          # manual CSV reader — relative date parsing
│   │   └── indeed.py            # RSS parser — blocked, retained for tests
│   ├── transformers/
│   │   ├── normalizer.py        # 29-column canonical schema, role taxonomy
│   │   ├── skill_extractor.py   # ~70-skill regex dictionary, alias collapsing
│   │   ├── salary_parser.py     # DE/EN salary formats, monthly → annual
│   │   └── deduplicator.py      # 2-pass: within-source + cross-source fuzzy
│   └── loaders/
│       └── duckdb_loader.py     # DELETE + INSERT upsert, views
├── analytics/
│   └── aggregations.py          # 5 SQL aggregation functions → DataFrames
├── airflow/dags/
│   └── job_market_pipeline.py   # daily DAG — parallel extract, dedup, load
├── dashboard/
│   ├── app.py                   # Streamlit app — sidebar filters, KPI row
│   └── charts.py                # Plotly chart builders
├── tests/                       # 347 tests, all offline (HTTP mocked)
│   ├── extractors/
│   ├── transformers/
│   ├── loaders/
│   ├── analytics/
│   └── test_pipeline_e2e.py
├── docs/
│   ├── schema.md
│   ├── decisions.md
│   ├── architecture.md
│   ├── sources.md
│   └── diagrams/architecture.svg
├── .github/workflows/
│   └── refresh.yml              # daily BA refresh + snapshot commit
└── requirements.txt
```

---

## Local setup

**Prerequisites:** Python 3.11, git.

```bash
# Clone
git clone https://github.com/adhishnanda/german-job-market-analytics.git
cd german-job-market-analytics

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Create data directories (gitignored)
mkdir -p data/raw data/processed data/db
```

**Run the pipeline:**

```bash
python -m etl.pipeline_runner
```

**Run the dashboard:**

```bash
streamlit run dashboard/app.py
```

**Run Airflow:**

```bash
airflow standalone
```

**LinkedIn data:** place a CSV export in `data/raw/linkedin/YYYY-MM-DD/` before running the pipeline. Template at `docs/linkedin_manual_template.csv`.

---

## Running tests

```bash
pytest tests/ -v
```

347 tests pass, 3 skipped. The suite runs entirely offline — all HTTP calls are mocked. No credentials or network access required.

```bash
# With coverage
pytest tests/ -v --cov=etl --cov-report=term-missing
```

---

## Known limitations

**Skill coverage is ~3.5%.** Bundesagentur and Stepstone search-result pages contain no description text - skill extraction only works on records with `description_raw`. Coverage improves if detail-page fetching is added.

**Salary data is sparse.** Most German job postings omit salary ranges. Parsed figures come from the subset that do and should not be treated as market-wide estimates.

**LinkedIn data is manual.** LinkedIn provides no public API or RSS feed. Data must be exported manually via LinkedIn's CSV export tool.

**Geographic scope is limited.** Stepstone and LinkedIn cover Berlin only. Bundesagentur covers 8 major German cities.

**Sampling, not census.** Six job-title keywords capture a representative but incomplete slice of the market.

---

## Author

**Adhish Nanda** - Data Science MSc candidate, Berlin

[Portfolio](https://adhishnanda.github.io) &nbsp;·&nbsp;
[GitHub](https://github.com/adhishnanda) &nbsp;·&nbsp;
[LinkedIn](https://linkedin.com/in/adhishnanda) &nbsp;·&nbsp;
adhish.nanda@gmail.com
