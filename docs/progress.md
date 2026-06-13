# Project Progress

## Week 1 — Foundation

### Day 1 — 2026-05-27
- [x] Scaffold project directory structure
- [x] Create requirements.txt
- [x] Create .gitignore
- [x] Create skeleton README.md
- [x] Initialize Git and make first commit (`b97487c`)
- [x] Create GitHub remote and push

### Day 2 — 2026-05-28
- [x] Test Bundesagentur API connection manually
- [x] Build etl/extractors/bundesagentur.py
- [x] Write tests/test_bundesagentur.py
- [x] Run tests and fix failures
- [x] Commit and push

### Day 3 — 2026-05-29
- [x] Build etl/transformers/normalizer.py
- [x] Build etl/transformers/skill_extractor.py
- [x] Write tests for both transformers
- [x] Run tests and fix failures
- [x] Commit and push (`7309872`)

### Day 4 — 2026-05-30
- [x] Build etl/transformers/salary_parser.py
- [x] Build etl/transformers/deduplicator.py
- [x] Write tests for both
- [x] Commit and push

### Day 5 — 2026-05-31
- [x] Build etl/loaders/duckdb_loader.py
- [x] Create jobs_raw table schema in DuckDB
- [x] Create jobs_clean view
- [x] Create skills_exploded view
- [x] Write tests with in-memory DuckDB
- [x] End-to-end test: BA extract → normalize → load
- [x] Commit and push

## Week 2 — Additional Sources

### Day 6 — 2026-05-30
- [x] Build etl/extractors/indeed.py (RSS route)
- [x] Test Indeed RSS parsing
- [x] Normalize Indeed records through existing transformer
- [x] Recreate .venv with Python 3.11; revert duckdb/pandas version bumps
- [x] Fix loader upsert for DuckDB 1.1.3 list-column compatibility
- [x] Commit and push

### Day 7 — 2026-05-30
- [x] Build etl/extractors/stepstone.py
- [x] Write tests/test_stepstone.py (41 tests)
- [x] Verify rate limiting, 403/429 handling, slug conversion
- [x] Commit and push

### Day 8
- [x] Create docs/linkedin_manual_template.csv
- [x] Build etl/extractors/linkedin.py (CSV reader)
- [x] Write tests/test_linkedin.py (37 tests)
- [x] Collect first 20 LinkedIn listings manually
- [x] Commit and push

### Day 9 — 2026-05-31
- [x] Validate linkedin_sample.csv: 20 rows, no missing job_id or title, all applicant_counts valid integers
- [x] Add city_raw auto-fill to "Berlin" when field is empty or missing (LinkedIn extractor)
- [x] Add _parse_relative_date: converts "N days/weeks/months/years ago" to approximate ISO date
- [x] Log four LinkedIn data-quality decisions in docs/decisions.md
- [x] Add _parse_posted_date to normalizer: handles YYYY-MM-DD, ISO 8601 with time, DD-MM-YYYY, RFC 2822
- [x] Add _normalize_stepstone and _normalize_linkedin to normalizer; update dispatch
- [x] Add 7 _parse_posted_date tests + Stepstone/LinkedIn normalizer tests (80 total in test_normalizer.py)
- [x] Build tests/test_pipeline_integration.py: 4-source fixture → normalize → deduplicate → load, 12 assertions
- [x] Commit and push

### Day 10 — 2026-05-31
- [x] Build etl/pipeline_runner.py (4-stage runner: extract → normalize → dedup → load + summary report)
- [x] Build etl/data_quality.py (5 checks: source dist, null rates, date range, dup rate, skill coverage)
- [x] Fix Stepstone _parse_cards: job ID moved to id="job-item-{n}", date now German timeago text
- [x] Add _parse_german_timeago to stepstone.py for "vor N Tagen/Wochen/..." patterns
- [x] Add max_pages parameter to stepstone.fetch_jobs for limited dry-run
- [x] Fix LinkedIn CSV encoding: try utf-8-sig → cp1252 fallback
- [x] Fix loader: drop_duplicates by job_id before INSERT (BA returns same job across keyword×city combos)
- [x] Full pipeline dry run: BA=853, Indeed=0 (blocked), Stepstone=25, LinkedIn=20 → 898 records → 543 in DB
- [x] Data quality run: Indeed blocked (flag), 63 old BA posts (expected), skill coverage 3.5% (structural)
- [x] Log all Day 10 findings in docs/decisions.md
- [x] Commit and push

## Week 3 — Airflow and Dashboard

### Day 11 — 2026-05-31
- [x] Install apache-airflow-providers-standard (FileSensor); Airflow upgraded 2.9.3 → 3.2.2
- [x] Build airflow/dags/job_market_pipeline.py: 6 tasks, @daily, FileSensor for LinkedIn CSV
- [x] Write tests/test_dag_loads.py: 9 tests verifying DAG structure offline
- [x] Update requirements.txt to pin apache-airflow==3.2.2 + providers-standard==1.13.1
- [x] Commit and push

### Day 12 — 2026-05-31
- [x] Build analytics/aggregations.py: five SQL aggregation functions over jobs_clean
- [x] Write tests/analytics/test_aggregations.py: 26 tests, in-memory DuckDB fixture
- [x] Fix pre-existing ruff F401/F541 warnings across 4 existing files (ruff --fix)
- [x] Commit and push

### Day 13 — 2026-05-31
- [x] Build dashboard/app.py — Streamlit skeleton, `@st.cache_resource` DuckDB read-only connection
- [x] Build dashboard/charts.py — `_apply_theme` shared helper, `skill_trend_chart`, `role_by_city_chart`, `role_donut_chart`
- [x] Add KPI row — canonical jobs, active sources, cities, role categories via `st.metric`
- [x] Add sidebar filters — posted date range, city multiselect, role category multiselect
- [x] Add `_filter_by_date`, `_filter_city`, `_filter_role` Python-level filter helpers
- [x] Wire all four aggregation functions from analytics/aggregations.py into dashboard
- [x] Inject dark editorial CSS — metric cards, chart container flush, spacing, sidebar divider
- [x] Commit and push

### Day 14 — 2026-05-31
- [x] Add `source_coverage_chart` and `language_ratio_chart` to charts.py
- [x] Salary distribution chart deferred — ~5–10% salary coverage too sparse for a meaningful chart at current data volumes; `salary_dist` aggregation ready when detail-page fetching lands
- [x] Load IBM Plex Mono + IBM Plex Sans via Google Fonts `@import` in CSS block
- [x] Apply IBM Plex Mono to axis labels, legend, metrics, hover; IBM Plex Sans to titles and body
- [x] Add `#00d4ff` 1px left-border accent to page title
- [x] Add uppercase letter-spaced section labels before each chart row (SKILL DEMAND TREND, ROLE BREAKDOWN, COVERAGE & LANGUAGE)
- [x] Polish: chart heights +20%, value-axis-only gridlines on bar charts, `hovermode="x unified"` on trend chart, `marker_line_width=0`, `y=0` reference line on bar charts, accent trace `line.width=3`
- [x] Confirm clean `streamlit run dashboard/app.py` start
- [x] Commit and push

## Week 4 — Polish and Deploy

### Day 15 — 2026-06-11
- [x] Slim requirements.txt to 4 dashboard-only runtime packages (duckdb==1.1.3, streamlit==1.36.0, plotly==5.22.0, pandas==2.2.2)
- [x] Create .streamlit/config.toml with dark editorial theme (base=dark, #111111/#1a1a1a/#e8e8e8/#00d4ff)
- [x] Remove data/db/ and *.duckdb from .gitignore; stage jobs.duckdb (2.26 MB) for Streamlit Cloud access
- [x] Fix ruff E402 warnings in dashboard/app.py (# noqa: E402 on post-sys.path imports)
- [x] black . && ruff check . — all checks passed

### Day 16 — 2026-06-11
- [x] Write full README.md with screenshots and methodology
- [x] Add architecture diagram to docs/architecture.md
- [x] Add data quality notes and coverage gaps disclosure
- [x] Commit and push

### Day 17 — 2026-06-13
- [ ] Write LinkedIn post draft
- [ ] Take dashboard screenshots for LinkedIn
- [ ] Final code review and cleanup
- [x] Tag v1.0.0 locally (`git tag -a v1.0.0`)

### Day 18 (buffer) — in progress
- [ ] Fix anything broken from real-world data
- [-] Add GitHub Actions workflow for scheduled BA refresh — `.github/workflows/refresh.yml` drafted, pending review
- [ ] Final push

## Notes
<!-- Add decisions, blockers, or observations here as you go -->