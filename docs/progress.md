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
- [ ] Build etl/transformers/salary_parser.py
- [ ] Build etl/transformers/deduplicator.py
- [ ] Write tests for both
- [ ] Commit and push

### Day 5 — 2026-05-31
- [ ] Build etl/loaders/duckdb_loader.py
- [ ] Create jobs_raw table schema in DuckDB
- [ ] Create jobs_clean view
- [ ] Write tests with in-memory DuckDB
- [ ] End-to-end test: BA extract → normalize → load
- [ ] Commit and push

## Week 2 — Additional Sources

### Day 6
- [ ] Build etl/extractors/indeed.py (RSS route)
- [ ] Test Indeed RSS parsing
- [ ] Normalize Indeed records through existing transformer
- [ ] Commit and push

### Day 7
- [ ] Build etl/extractors/stepstone.py
- [ ] Test on 1 keyword × 1 page only
- [ ] Verify rate limiting works
- [ ] Commit and push

### Day 8
- [ ] Create docs/linkedin_manual_template.csv
- [ ] Document manual LinkedIn collection process
- [ ] Build etl/extractors/linkedin.py (CSV reader)
- [ ] Collect first 20 LinkedIn listings manually
- [ ] Commit and push

### Day 9
- [ ] Build cross-source deduplicator
- [ ] Test dedup logic with sample data from 2+ sources
- [ ] Verify is_duplicate and canonical_id fields
- [ ] Commit and push

### Day 10
- [ ] Full pipeline dry run: all 4 sources → normalize → deduplicate → load
- [ ] Check data quality: null rates, duplicate rate, posting date range
- [ ] Fix any issues
- [ ] Commit and push

## Week 3 — Airflow and Dashboard

### Day 11
- [ ] Set up Airflow locally (airflow standalone)
- [ ] Build airflow/dags/job_market_pipeline.py skeleton
- [ ] Define 4 extract tasks + downstream tasks
- [ ] Test DAG loads without errors
- [ ] Commit and push

### Day 12
- [ ] Build analytics/aggregations.py (skill counts, role counts, salary dist)
- [ ] Write and test core SQL queries in DuckDB
- [ ] Commit and push

### Day 13
- [ ] Build dashboard/app.py — Streamlit skeleton + DuckDB connection
- [ ] Add skill demand over time chart
- [ ] Add role count by city chart
- [ ] Commit and push

### Day 14
- [ ] Add salary distribution by role chart
- [ ] Add source coverage comparison chart
- [ ] Add English vs German ratio chart
- [ ] Add sidebar filters (date, city, role category)
- [ ] Commit and push

## Week 4 — Polish and Deploy

### Day 15
- [ ] Deploy Streamlit app to Streamlit Cloud
- [ ] Test live deployment
- [ ] Add live demo link to README.md
- [ ] Commit and push

### Day 16
- [ ] Write full README.md with screenshots and methodology
- [ ] Add architecture diagram to docs/architecture.md
- [ ] Add data quality notes and coverage gaps disclosure
- [ ] Commit and push

### Day 17
- [ ] Write LinkedIn post draft
- [ ] Take dashboard screenshots for LinkedIn
- [ ] Final code review and cleanup
- [ ] Tag v1.0.0 release on GitHub

### Day 18 (buffer)
- [ ] Fix anything broken from real-world data
- [ ] Add GitHub Actions workflow for scheduled BA refresh
- [ ] Final push

## Notes
<!-- Add decisions, blockers, or observations here as you go -->