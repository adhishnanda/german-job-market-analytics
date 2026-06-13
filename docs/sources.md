# Source Reference

## Overview

| Source | Method | ID prefix | Sleep between requests | Schedule | Status |
|---|---|---|---|---|---|
| Bundesagentur für Arbeit | REST API v6 | `BA_` | 2 s (fixed) | Daily (Airflow) | Active |
| Indeed Germany | RSS feed (feedparser) | `IN_` | 3 s (theoretical) | — | **BLOCKED (HTTP 403)** |
| Stepstone | HTML scraping (requests + BS4) | `SS_` | 10–18 s random | Daily (Airflow) | Active |
| LinkedIn | Manual CSV export | `LI_` | n/a | Manual trigger | Active (manual) |

---

## Bundesagentur für Arbeit (`BA_`)

### Endpoint / access method

REST API v6 — `GET https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs`

Required headers:
- `X-API-Key: jobboerse-jobsuche` (no OAuth required)
- Browser-like `User-Agent` — the Python default `requests` UA fails the WAF check

Pagination: `page` parameter is 1-indexed; total result count is in `maxErgebnisse`; records are in `ergebnisliste`. Page size is 25 (`size=25`).

### Coverage

6 keywords × 8 cities (48 combinations per run):

| Keywords | Cities |
|---|---|
| Data Engineer, Data Analyst, Data Scientist, Analytics Engineer, BI Engineer, Machine Learning Engineer | Berlin, Munich, Hamburg, Frankfurt, Cologne, Stuttgart, Düsseldorf, Leipzig |

### Fields available

| API field | Canonical field | Notes |
|---|---|---|
| `referenznummer` | `job_id` → `BA_{referenznummer}` | Unique across BA; same job recurs across keyword×city queries |
| `stellenangebotsTitel` | `title_raw` | |
| `firma` | `company` | |
| `stellenlokationen[0].adresse.ort` | `city` | |
| `stellenlokationen[0].adresse.plz` | `postal_code` | BA is the only source with this field |
| `stellenlokationen[0].breite` | `lat` | BA is the only source with coordinates |
| `stellenlokationen[0].laenge` | `lon` | |
| `stellenlokationen[0].adresse.region` | `region` | German federal state |
| `veroeffentlichungszeitraum.von` | `posted_date` | ISO date string |
| `arbeitszeitVollzeit` | `employment_type` | Structured boolean; no regex needed |
| `homeofficetyp` | `work_model` | Structured enum; no regex needed |
| *(not in search list)* | `description_raw` | Always `""` — requires a separate detail-endpoint call that was not implemented |

### Known limitations

- `description_raw` is absent from search-list results — a separate detail endpoint call is needed and was deferred. Skill extraction is near-zero for BA records.
- The same `referenznummer` recurs across multiple keyword × city combinations. The loader deduplicates these before the `PRIMARY KEY` constraint fires.
- BA's full active index includes postings from 2022–2025 that remain live. This causes the 90-day date-range quality check to fail permanently.

### Sleep / rate-limit policy

`SLEEP_SECONDS = 2.0` — fixed 2 s sleep between every pagination request.

---

## Indeed Germany (`IN_`)

### Endpoint / access method

RSS feeds via `feedparser`: `https://de.indeed.com/rss?q={keyword}&l={location}&sort=date`

5 feeds targeted:

| Keyword | Location |
|---|---|
| Data Analyst | Berlin |
| Business Intelligence | Deutschland |
| Analytics Engineer | Berlin |
| Data Engineer | Berlin |
| Data Scientist | Berlin |

### Fields available (theoretical — no live data)

| RSS field | Canonical field | Notes |
|---|---|---|
| `guid` | `job_id` → `IN_{guid}` | |
| `title` | `title_raw` | |
| `author` | `company` | |
| `location` | `city` | Parsed from free text |
| `published` | `posted_date` | RFC 2822 format: `"Mon, 27 May 2026 10:00:00 GMT"` |
| `link` | `url` | |
| `summary` | `description_raw` | Would provide skill-extraction signal |

### Known limitations

**All five `de.indeed.com/rss` feeds return HTTP 403 on every run.** No live data has ever been collected. The extractor returns `[]` gracefully. HTML scraping was rejected (legal ambiguity and faster blocking). The extractor code, fixture-based tests, the `IN_` prefix, and the deduplicator priority slot (index 1) are all retained in place to avoid disrupting cross-source dedup logic and to allow re-enablement if a compliant access path becomes available.

### Sleep / rate-limit policy

`SLEEP_SECONDS = 3.0` — 3 s between feed requests (theoretical; not exercised in practice since all feeds 403 immediately).

---

## Stepstone (`SS_`)

### Endpoint / access method

HTML scraping: `GET https://www.stepstone.de/jobs/{keyword-slug}/in-{location}`

Library stack: `requests` + `BeautifulSoup4`. **Not** Playwright or `requests-html` — both trigger detection and blocking faster.

5 keyword slugs × 1 location × max 2 pages per slug:

| Slugs | Location |
|---|---|
| `data-analyst`, `business-intelligence`, `analytics-engineer`, `data-engineer`, `data-scientist` | `berlin` |

### Fields available

| Source element | Canonical field | Notes |
|---|---|---|
| `id="job-item-{n}"` attribute on card | `job_id` → `SS_{internal_id}` | Moved from `data-job-id` attr during Day 10 — see Known Limitations |
| Job title element | `title_raw` | |
| Company name element | `company` | |
| Location element | `city` | |
| `<time>` text: `"vor N Tagen"` / `"Heute"` / `"Gestern"` | `posted_date` | German relative string; parsed via `_parse_german_timeago`; no `datetime` attribute |
| `<a>` href on card | `url` | |
| *(not present)* | `description_raw` | Always `""` — search-result cards only; no detail page fetched |

### Known limitations

- `description_raw` is always `""` — Stepstone search-result cards show title and metadata only. Skill extraction is zero for this source until detail-page fetching is implemented.
- Geographic scope: Berlin only.
- Posted date is an approximate German relative string; `_parse_german_timeago` uses 1 Monat = 30 days, 1 Jahr = 365 days (±2 day accuracy).
- On HTTP 403 or 429: extractor aborts remaining pages for the current keyword slug and continues to the next slug.
- HTML structure changed once during development (Day 10): the job ID moved from a `data-job-id="..."` attribute to `id="job-item-{n}"` on the card element. The posted date moved from `<time datetime="YYYY-MM-DD">` to `<time>vor N Tagen</time>` with no `datetime` attribute. Both are handled in the current `_parse_cards` implementation.

### Sleep / rate-limit policy

`random.uniform(SLEEP_MIN, SLEEP_MAX)` — `SLEEP_MIN = 10.0`, `SLEEP_MAX = 18.0`. Random sleep applied between **every** page request, not just between keyword slugs. Hardcoded sleep times are prohibited; always use `random.uniform`.

---

## LinkedIn (`LI_`)

### Endpoint / access method

Manual CSV export — no scraping or API calls. The user exports LinkedIn job search results, saves the CSV at:

```
data/raw/linkedin/YYYY-MM-DD/{filename}.csv
```

`etl/extractors/linkedin.py` is a CSV reader, not a scraper. CSV template: `docs/linkedin_manual_template.csv`.

The Airflow DAG uses a `FileSensor` watching `data/raw/linkedin/{{ ds }}/`. If no CSV is placed before the sensor times out, the LinkedIn normalise task is skipped for that day.

### Fields available

| CSV column | Canonical field | Required? | Notes |
|---|---|---|---|
| `job_id_raw` | `job_id` → `LI_{job_id_raw}` | Required | |
| `title_raw` | `title_raw` | Required | |
| `company_raw` | `company` | Optional | |
| `city_raw` | `city` | Optional | Defaults to `"Berlin"` when blank |
| `posted_at_raw` | `posted_date` | Optional | Relative ("N days ago") or ISO or DD-MM-YYYY |
| `description_raw` | `description_raw` | Optional | Typically absent from LinkedIn export |
| `url` | `url` | Optional | |
| `employment_type` | `employment_type` | Optional | |
| `applicant_count` | *(stored in raw, not in canonical schema)* | Optional | |
| `is_remote` | `work_model` | Optional | `True` → `HYBRID` (covers both remote and hybrid — LinkedIn does not distinguish) |

### Known limitations

- Not on the Airflow daily schedule — must be manually collected and placed before each pipeline run.
- `posted_at_raw` is a relative timestamp ("N days ago") converted to an approximate ISO date; accuracy is ±2 days.
- `is_remote=True` maps to `HYBRID` because LinkedIn's export does not distinguish fully remote from hybrid. There is no way to recover the true `REMOTE` vs `HYBRID` split from LinkedIn CSV exports.
- `city_raw` defaults to `"Berlin"` when blank because all LinkedIn collection in this project is scoped to Berlin searches.
- CSV encoding: `_read_csv` tries `utf-8-sig` first, then falls back to `cp1252`. Windows-exported CSVs often arrive as `cp1252`.
- `description_raw` is typically not included in LinkedIn's standard job search export; as a result, LinkedIn records rarely contribute to skill extraction.

### Sleep / rate-limit policy

n/a — no HTTP requests are made. The extractor reads only local CSV files already placed on disk.
