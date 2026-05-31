# Architecture Decisions

## 2026-05-27 — Initial scaffold

### Dependency pinning strategy
All packages in `requirements.txt` are pinned to exact versions (`==`).
Reason: scraping projects are brittle — a minor feedparser or bs4 bump can
silently change parsing behaviour and corrupt the historical dataset.
Trade-off: manual version bumps required; accepted given the small team size.

### Chart libraries: Plotly + Altair both included
Both `plotly` and `altair` are listed as dependencies because Streamlit has
native support for both and they cover complementary use cases (Plotly for
interactive drill-down, Altair for declarative layered charts). Whichever
works best for a given chart will be used; the other can be dropped later
without breaking anything.

### DuckDB as the only storage layer
No separate Postgres or SQLite. DuckDB handles all analytical queries
directly on `.duckdb` files stored in `data/db/`. This keeps the stack
self-contained — no server to run — and DuckDB's columnar engine is
well-suited to the aggregation-heavy dashboard queries.

### `data/` directories gitignored but scaffolded with `.gitkeep`
The `.gitkeep` files themselves are gitignored (parent dirs are in
`.gitignore`) so `data/raw/`, `data/processed/`, and `data/db/` will not
exist on a fresh clone. Fresh-clone setup step: `mkdir -p data/{raw,processed,db}`.
This will be added to README setup instructions when the first extractor lands.

### Stub pattern: `raise NotImplementedError`
Skeleton functions raise `NotImplementedError` rather than returning empty
lists. Empty-list stubs would let tests pass silently on unimplemented code;
`NotImplementedError` makes the gap obvious and forces the test to be skipped
explicitly (`pytest.skip`) until the real implementation exists.

## 2026-05-28 — Bundesagentur API (Day 2 live testing)

### BA API version: v6, not v4
During live connection testing the v4 endpoint (`/pc/v4/jobs`) returned 403 for
all requests. Investigation via the Angular app's `config/config.js` revealed
the active endpoint is `/pc/v6/jobs`.

### API key: `jobboerse-jobsuche`
The key embedded in the BA Jobsuche SPA is `jobboerse-jobsuche` (previously
`jobboerse-jobsuche-ui` in older versions of the app). Passed as `X-API-Key`
header. No OAuth Bearer token is required for the public search endpoint.

### v6 pagination is 1-indexed
The `page` query parameter in v6 starts at 1 (not 0). Sending `page=0` returns
a 400 with `"must be greater than or equal to 1"`. The extractor initialises
each keyword × city loop at `page = 1`.

### v6 response field names differ from v4
| v4 field | v6 field |
|---|---|
| `stellenangebote` | `ergebnisliste` |
| `hashId` | `referenznummer` |

`maxErgebnisse` is unchanged. The extractor and tests were updated to use the v6
field names; the `BA_` prefix uses `referenznummer` as the raw ID.

### Browser User-Agent required
The API gateway applies a WAF rule that varies on `User-Agent`. A browser-like
string (`Mozilla/5.0 … AppleWebKit/537.36`) passes through; a Python or curl
default does not. The `_HEADERS` dict in the extractor uses a Chrome UA.

### Airflow DAG: `@daily`, `catchup=False`
The DAG is set to run once per day with no historical backfill. Bundesagentur
and Indeed data is near-real-time; backfilling old dates would produce
incomplete snapshots anyway. This can be revisited once a stable historical
baseline exists.

## 2026-05-29 — Normalizer and skill extractor (Day 3)

### Role taxonomy: ordered list, first match wins
`_ROLE_TAXONOMY` in `normalizer.py` is a `list[tuple]`, not a dict, so match
order is deterministic and explicit. A title like "ML Engineer" would satisfy
both the "Data Science / ML" bucket (which contains "ml engineer") and the
"ML Engineering" bucket. By placing "Data Science / ML" above "ML Engineering"
in the list the intent is clear: a bare "ML Engineer" title defaults to the
broader science/ML grouping. The order can be changed without touching the
matching logic.
Trade-off: "ML Engineering" as a separate bucket is currently hard to reach
because "ml engineer" is caught by "Data Science / ML" first. This is
intentional for now — the bucket exists to catch compound titles like
"MLOps / ML Engineering" where "ml engineer" appears alongside "mlops".

### Role category falls through to "Other"
The normalizer returns "Other" rather than `None` when no taxonomy keyword
matches. A string value is easier to filter and group in SQL (`WHERE
role_category = 'Other'`) than a `NULL` which requires `IS NULL` handling.

### Skill matching: regex `\b` word boundaries, case-insensitive, compiled at import
Each entry in `SKILL_MAP` compiles its patterns into a single `re.Pattern`
with `re.IGNORECASE` at module load time (`_COMPILED`). Advantages:
- Compilation cost paid once, not per record.
- `\b` prevents substring false-positives (e.g. "Scala" matching inside
  "Rescala" or "R" matching every word containing the letter).
- Aliases (e.g. `GCP` → `Google Cloud Platform`) are handled by listing
  multiple patterns under one canonical key; the canonical name is what goes
  into the `skills` array.
No fuzzy matching was used — the false-positive rate on job descriptions
outweighs the small recall gain from approximate matching.

### Skill deduplication: dict key insertion order, not set
`extract_skills` accumulates matches in a `dict[str, None]` rather than a
`set`. Both deduplicate, but `dict` preserves the SKILL_MAP iteration order,
giving a stable, predictable output order in the `skills` array. This makes
snapshot diffs readable and tests deterministic without requiring a sort.

### `skills` initialized as `[]` in normalizer, filled separately
The normalizer sets `skills: []` and does not call `extract_skills`. The
two steps are intentionally decoupled: the skill dictionary can be expanded
and re-run over stored normalized records without re-fetching or re-parsing
raw data. The caller (pipeline or loader) is responsible for wiring the two
steps together.

## 2026-05-30 — Salary parser and deduplicator (Day 4)

### Single salary figure: salary_min = salary_max
When only one numeric value is found in `salary_raw` (e.g. `"€60.000"`), both
`salary_min` and `salary_max` are set to that value rather than leaving one as
`NULL`. A point estimate treated as a range keeps the dashboard consistent —
all salary comparisons and bucket queries can use `salary_min`/`salary_max`
uniformly without special-casing single values.
Trade-off: loses the distinction between "we know both endpoints" and "we know
only one figure", but that signal is not used anywhere in the current pipeline.

### Currency defaults to EUR
`_detect_currency` returns `"EUR"` when no currency symbol is present in
`salary_raw`. The dataset is German-market only; an undecorated number like
`"50000"` is almost certainly EUR. Explicit `$`/`USD` and `£`/`GBP` symbols
override the default.

### Dedup city guard: hard requirement, skip if either city is None
`_is_cross_source_match` returns `False` immediately if either record has
`city = None`, rather than falling through to company+title+date matching.
Reason: without a location anchor the false-positive rate is too high — the
same role title at the same company can exist in multiple cities simultaneously
(e.g. "Data Engineer" at SAP in Berlin and Munich). Cross-source dedup without
city would incorrectly collapse genuinely distinct postings.
The same hard-skip applies to `posted_date`.

### Pass 2 dedup: sort by priority, walk highest-to-lowest
Cross-source deduplication collects all surviving canonical records, sorts them
by `_SOURCE_PRIORITY` (bundesagentur=0, indeed=1, stepstone=2, linkedin=3),
then iterates from the top. Each record is checked against a `locked` list of
already-processed higher-priority records; if a match is found the current
record is marked duplicate and skipped, otherwise it joins `locked`.
This single-pass approach is O(n²) in the number of cross-source canonicals
but avoids any graph-resolution complexity. At expected dataset sizes (hundreds
to low thousands of postings per run) the cost is negligible.
Alternative considered: build a graph of matched pairs and resolve connected
components. Rejected — overkill for the dataset size and harder to reason about
priority ordering across multi-hop matches.

### `language` defaults to `"unknown"`, never raises
`_detect_language` catches `LangDetectException` and returns `"unknown"`
rather than propagating. Short descriptions (< ~20 chars), empty strings, and
purely numeric text all fail detection; silently returning `"unknown"` keeps
the record usable. `NULL` was avoided for the same reason as role_category —
string comparisons are simpler in SQL aggregations.

### Enum fields return `"UNKNOWN"`, not `None`, on missing data
`_map_work_model` and `_map_employment_type` return the string `"UNKNOWN"`
when the source field is absent or unrecognised. This keeps `work_model` and
`employment_type` non-null in every record, which simplifies GROUP BY and
filter queries in the dashboard layer.

## 2026-05-31 — DuckDB loader (Day 5)

### Upsert via INSERT OR REPLACE INTO
The loader uses `INSERT OR REPLACE INTO jobs_raw` rather than
`INSERT INTO … ON CONFLICT DO UPDATE`. DuckDB supports both; `INSERT OR REPLACE`
is simpler — it replaces the entire row on a `PRIMARY KEY` conflict — and the
pipeline always re-derives every field from fresh source data, so partial-update
semantics offer no benefit here. The tradeoff is that partial re-runs (only some
fields changed) also replace the entire row, but that is fine for this pipeline.

### load_to_connection separated from load
`load_to_connection(jobs, conn)` is the testable core; `load(jobs, db_path)` is
a thin wrapper that opens the connection and delegates. This lets tests inject an
in-memory DuckDB connection without touching the filesystem.

### DataFrame registration for bulk upsert
Records are converted to a pandas DataFrame, registered with DuckDB as a view
(`conn.register("_staging", df)`), then inserted via SQL. This is cleaner than
`executemany` (which requires manual type coercion for `DATE`, `BOOLEAN`,
`VARCHAR[]`) and avoids building a large `VALUES (…)` clause.

### fetched_at stored as tz-naive TIMESTAMP
The normalizer produces a timezone-aware `datetime` (UTC). DuckDB's `TIMESTAMP`
type is tz-naive. The loader strips `tzinfo` before insertion — the value is
always UTC so stripping is lossless, and it avoids DuckDB type-mismatch errors.

### skills_exploded excludes duplicate records
The `skills_exploded` view filters `is_duplicate = FALSE`, matching `jobs_clean`.
Dashboard skill counts should not be inflated by duplicate postings; the view
being consistent with `jobs_clean` removes the need for callers to remember an
extra filter.

### Package versions reverted to Python 3.11 originals (Day 6)
The Day 5 bumps (`duckdb==1.5.3`, `pandas==3.0.3`) were made for Python 3.14
wheel availability. The project uses Python 3.11 per CLAUDE.md; reverting to
`duckdb==1.1.3` and `pandas==2.2.2` restores the originally-pinned versions,
which ship 3.11 wheels and work on all target environments.

## 2026-05-30 — Stepstone extractor (Day 7)

### Slug conversion: lowercase + umlaut transliteration + hyphenate non-alphanum
`_to_slug` lowercases, maps German umlauts (ä→ae, ö→oe, ü→ue, ß→ss) via
`str.maketrans`, then collapses any run of non-alphanumeric characters to a
single hyphen with `re.sub`. Leading/trailing hyphens are stripped.
This matches Stepstone's URL pattern exactly without requiring a third-party
slugify library.

### _fetch_page returns the raw Response; status-code logic lives in fetch_jobs
`_fetch_page` catches `RequestException` (connection errors) and returns None;
otherwise it returns the `Response` unchanged so the caller can inspect the
status code. Keeping status-code branching in `fetch_jobs` makes the 403/429
"stop keyword" behaviour testable without mocking at the session level.

### 403/429: stop keyword, not entire run
A `blocked` flag is set when a 403 or 429 arrives; it breaks out of both the
page loop and the location loop for that keyword, then the outer keyword loop
continues normally. Other HTTP errors (5xx, etc.) break only the page loop —
another location for the same keyword can still be tried.

### Sleep before every request except the first (global counter)
A module-level `request_count` integer tracks total requests across all
keyword × location × page iterations. Sleep is skipped only when
`request_count == 0` (the very first request). This matches the BA and Indeed
pattern and ensures the 10–18 s gap is always observed between consecutive
Stepstone requests regardless of keyword or page boundaries.

### Snapshot format: JSON, one file per run
Stepstone records are saved as a single `stepstone.json` in the dated
subdirectory, matching the Bundesagentur snapshot format. CSV was not used
because `VARCHAR[]` skill fields added later would require quoting gymnastics.

### Upsert strategy: DELETE + INSERT, no explicit transaction (Day 6)
`INSERT OR REPLACE` fails on DuckDB 1.1.3 with `VARCHAR[]` columns
(`NotImplementedException: List Update is not supported`). The replacement
strategy is an explicit `DELETE FROM jobs_raw WHERE job_id IN (SELECT job_id
FROM _staging)` followed by `INSERT INTO jobs_raw … SELECT … FROM _staging`.
Wrapping these in an explicit `BEGIN/COMMIT` block prevented the `_staging`
registered view from being visible inside the transaction in DuckDB 1.1.3,
causing the DELETE to silently match nothing. Removing `BEGIN/COMMIT` and
relying on per-statement auto-commit resolves both issues. Atomicity is not a
practical concern for an in-process, single-writer pipeline.

## 2026-05-31 — LinkedIn extractor data quality (Day 9)

### posted_at_raw is approximate for LinkedIn (±2 days)
LinkedIn's UI shows relative timestamps ("2 weeks ago", "3 days ago") rather
than absolute dates. The extractor converts these to ISO dates using fixed
multiples (1 month = 30 days, 1 week = 7 days, 1 year = 365 days). The
converted value can be off by up to ±2 days from the actual posting date.
`posted_at_raw` stores the already-converted ISO string (not the original
relative phrase) so downstream normalisation does not need to handle two date
formats. Unrecognised strings (e.g. "last quarter") pass through unchanged.

### applicant_count capped at 100 by LinkedIn UI
LinkedIn truncates the applicant count display at "100+ applicants" and does
not expose the real number via its public UI. Values manually entered above 100
should be treated as the sentinel "at least 100". The extractor accepts any
integer but callers should not rely on precision above 100. Non-integer values
(e.g. "over 200") are logged as warnings and stored as `NULL`.

### is_remote=True covers both remote and hybrid roles
LinkedIn's search-result badge does not distinguish "fully remote" from
"hybrid". Both appear as "Remote" in the UI, so `is_remote = True` in the CSV
means only "not fully on-site". The normalizer maps this to
`work_model = "UNKNOWN"` until LinkedIn exposes a structured work-model field
that separates the two.

### posted_at_raw date format: DD-MM-YYYY in manual CSV
Dates copied from LinkedIn's UI appear as DD-MM-YYYY (e.g. "30-05-2026"), not
ISO format. The extractor passes these through unchanged (they don't match the
relative-date pattern). The normalizer must handle both DD-MM-YYYY and ISO
(YYYY-MM-DD) strings for this field.

### city_raw auto-filled to "Berlin" for LinkedIn manual collection
The manual CSV collection workflow sometimes omits the city field. The
extractor defaults empty or missing `city_raw` to `"Berlin"` because the
collection is scoped to Berlin-area roles. This prevents `NULL` city values
that would cause the deduplicator's city guard to silently drop cross-source
matches for otherwise valid records.

## 2026-05-31 — Day 10 pipeline dry run findings

### Indeed RSS feeds permanently blocked
All five `de.indeed.com/rss` feeds return HTTP 403 or 404 as of 2026-05-31.
Indeed has shut down or geo-blocked public RSS access for this endpoint.
The extractor returns `[]` gracefully and the data-quality source-distribution
check flags Indeed as missing on every run — that flag is expected until a
replacement is in place.
Plan: Week 3 will evaluate an HTML scraping fallback for Indeed search results
using the same approach as Stepstone. If the HTML route is also blocked or
legally ambiguous, Indeed will be dropped from the active source list entirely.
No pipeline code changes required in the interim.

### Indeed dropped as active source — final decision
The live run confirmed HTTP 403 across all five RSS endpoints on every attempt.
The Week 3 HTML-scraping evaluation was cancelled: attempting to scrape
Indeed's HTML search results carries higher legal ambiguity than Stepstone, and
the live run results leave no room for doubt about the RSS route. Indeed is
removed from the active pipeline as of 2026-05-31.
Code retention: `etl/extractors/indeed.py` and its fixture-based tests remain
in the repo. The extractor can be re-enabled if a compliant access path exists
later (e.g. an official partner API). The `IN_` job-ID prefix and deduplicator
priority slot (index 1) are left in place to avoid disrupting cross-source
dedup logic if Indeed is re-added.
Active sources going forward: Bundesagentur, Stepstone, LinkedIn.
README updated to reflect this.

### Stepstone HTML breaking change: job ID and date fields
Stepstone's search-results HTML changed between Day 7 and Day 10:
- Job ID moved from `data-job-id="..."` attribute to `id="job-item-{id}"`.
- Posted date moved from `<time datetime="YYYY-MM-DD">` to `<time>vor N Tagen</time>`
  (German relative string, no `datetime` attribute).
Both fields required parser updates in `_parse_cards`. A German relative-date
parser (`_parse_german_timeago`) was added to stepstone.py, covering "vor N
Tagen/Wochen/Monaten/Jahren", "Heute", and "Gestern".
Two Stepstone cards (8%) had no `<time>` tag at all — `posted_date` is NULL for
those records. This is within the 20% null-rate threshold.

### BA API returns historical listings (up to 3+ years old)
The live BA API search-result feed includes job postings from 2022 and 2023 that
are still technically "open" in the system. Of 498 canonical BA records loaded:
- 2 records from 2022–2023 (genuinely old, still in BA's index)
- 31 records from 2025 (>90 days, still active)
- 465 records from 2026 (current)
This is expected behaviour — the BA API exposes its full active index without a
recency filter. The date range FAIL from data_quality.py is not a data error.
Decision: raise the date-range threshold in `data_quality.py` from 90 days to
180 days for the BA source only. This still catches genuinely stale or misdated
records (2022–2023 outliers stay flagged) while not raising a false alarm for
the large proportion of legitimately older-but-active BA listings.

### Skill coverage low (3.5%) — structural, not a bug
Only 19 of 541 canonical records have at least one skill detected. The root
cause is structural: BA search-list records include only title and metadata
(no description text); Stepstone search cards also return no description.
`skill_extractor` can only find skills in `description_raw`, so coverage is
bounded by the fraction of records that have a non-empty description.
Two paths to improvement:
1. Fetch individual job detail pages for BA and Stepstone (future iteration).
   This would make description available for ~95% of records.
2. Rely on LinkedIn and Indeed (when unblocked) as the primary skill-signal
   sources until detail-page fetching is implemented.
The 50% coverage threshold in `data_quality.py` remains as-is; the flag is
expected on every run until detail-page fetching lands.

### Loader dedup fix: drop_duplicates by job_id before INSERT
The BA API returns the same `referenznummer` (and therefore same `BA_{id}`) for
the same job posting across multiple keyword × city search combinations.
The deduplicator marks the second and later occurrences as `is_duplicate=True`,
but all occurrences share the same `job_id`. DuckDB's `job_id PRIMARY KEY` then
rejects the second INSERT with a constraint error.
Fix: in `load_to_connection`, sort records by `is_duplicate` ascending (canonical
first) then `drop_duplicates(subset="job_id", keep="first")` before building the
staging DataFrame. This ensures each `job_id` is inserted exactly once,
preserving the canonical version's `is_duplicate=False` value.
Cross-source duplicates (e.g. `LI_456` pointing to `BA_123`) have distinct
`job_id` values and are unaffected — both records are stored.

### LinkedIn CSV encoding: cp1252 fallback
The manually collected `linkedin_sample.csv` was saved on Windows with
cp1252 encoding (Windows-1252), not UTF-8. Byte `0xF6` (ö) caused a
`UnicodeDecodeError` when `_read_csv` opened the file with `encoding="utf-8"`.
Fix: `_read_csv` now tries `utf-8-sig` first (handles UTF-8 with BOM), then
falls back to `cp1252`. If both fail a `ValueError` is raised with the file
path so the caller knows which CSV needs re-encoding.
Documented for reproducibility: any future manual CSVs exported from Excel or
a Windows browser should be checked with `file -i` or saved explicitly as
UTF-8 to avoid silent field-corruption on non-Windows hosts.

## 2026-05-31 — Normalizer date unification (Day 9)

### _parse_posted_date replaces per-source inline parsing
All four sources use different date formats: BA/standard ISO (YYYY-MM-DD),
Stepstone ISO 8601 with time (e.g. "2026-05-30T10:00:00"), LinkedIn manual
DD-MM-YYYY, and Indeed RSS RFC 2822. Previously BA parsed inline and Indeed
used a dedicated `_parse_rfc2822_date` helper; Stepstone and LinkedIn had no
normalizer at all.
`_parse_posted_date` tries the formats in order (ISO slice → DD-MM-YYYY strptime
→ parsedate_to_datetime) and logs a warning returning None for anything
unrecognised. Centralising the logic means adding a new date format requires
touching one function, not four.

### _normalize_stepstone maps location_raw → city; no description available
The Stepstone extractor scrapes search-result cards only — no detail-page fetch.
`description_raw` is therefore always `""` at normalisation time, which means
`employment_type`, `work_model`, and `skills` default to "UNKNOWN" / []. The
fields remain available to be populated if a description-fetch step is added
later without changing the schema.

### _normalize_linkedin: is_remote=True → work_model="UNKNOWN"
Matches the decision logged in the LinkedIn extractor data-quality section above.
The employment_type hint concatenates the raw CSV `employment_type` column with
`description_raw` before keyword scanning, so CSV values like "Full-time" are
matched by the same `\bfull[\-\s]?time\b` regex used for other sources.

## 2026-05-31 — Airflow DAG (Day 11)

### Airflow upgraded from 2.9.3 to 3.2.2
Installing `apache-airflow-providers-standard` (required for `FileSensor`) caused
pip to resolve and install `apache-airflow==3.2.2`, replacing the pinned 2.9.3.
The upgrade was accepted rather than fought: Airflow 3.x is the current stable
release, and the pipeline's DAG logic is simple enough that the migration cost was
low. `requirements.txt` now pins `apache-airflow==3.2.2` and adds
`apache-airflow-providers-standard==1.13.1` as an explicit dependency.

### days_ago replaced with pendulum.now("UTC").subtract(days=1)
`airflow.utils.dates.days_ago` was removed in Airflow 3.0. The DAG
`start_date` now uses `pendulum.now("UTC").subtract(days=1)`, which is the
idiomatic Airflow 3.x equivalent. `pendulum` is a direct dependency of
apache-airflow and is available without a separate install.

### dag.schedule_interval removed in Airflow 3.x; use dag.schedule
The `DAG.schedule_interval` attribute was removed in Airflow 3.0. The stored
schedule string is now accessed via `dag.schedule`, which returns `"@daily"` when
the DAG is constructed with `schedule="@daily"`. The test suite checks
`dag.schedule == "@daily"` accordingly.

## 2026-05-31 — SQL aggregations layer (Day 12)

### Five aggregation functions, each accepting an open connection
`analytics/aggregations.py` exposes five functions — `skill_demand_weekly`,
`role_by_city`, `salary_dist`, `language_ratio`, `source_coverage` — each taking
a `duckdb.DuckDBPyConnection` and returning a `pd.DataFrame`.
Reason for the connection-injection pattern: the dashboard will hold one
long-lived read-only connection opened against `data/db/jobs.duckdb`; injecting
it avoids opening and closing a file-backed connection on every chart render, and
lets tests substitute an in-memory connection without any mocking.

### All queries target jobs_clean, not jobs_raw
Every function queries the `jobs_clean` view (`WHERE is_duplicate = FALSE`) or
the `skills_exploded` view (which also filters `is_duplicate = FALSE`). Querying
`jobs_raw` directly would require each function to repeat the duplicate filter;
using the views makes the de-duplication invariant impossible to forget.

### skill_demand_weekly queries skills_exploded, not jobs_clean
Skills live in a `VARCHAR[]` array on `jobs_raw`. To count per-skill per-week,
the array must be unnested into one row per skill. The `skills_exploded` view
already performs this unnest and inherits the `is_duplicate = FALSE` filter, so
`skill_demand_weekly` queries that view directly rather than calling
`UNNEST(skills)` inside the aggregation function itself.
`DATE_TRUNC('week', posted_date)` truncates to the ISO Monday of the week.
Records with `posted_date IS NULL` are excluded — their week bucket is unknown
and grouping them as `NULL` would mislead the dashboard time axis.

### salary_dist filters WHERE salary_min IS NOT NULL at the SQL level
Salary data is sparse (~5–10% of records have a salary). Returning all canonical
records and letting the caller drop nulls would give the dashboard a large mostly-
null DataFrame. Filtering in SQL keeps the returned DataFrame compact and makes
the semantics of the function explicit in its query.

### language_ratio uses a two-CTE pattern to compute per-source percentages
A `base` CTE groups by `(source, language)` to get counts; a `totals` CTE sums
per source; the outer query joins them to compute `pct = count / total`.
Alternative considered: a window function (`COUNT(*) OVER (PARTITION BY source)`).
Rejected because the CTE pattern is more readable and explicitly separates the
two aggregation levels. The `pct` is rounded to 4 decimal places — enough
precision for a percentage display without floating-point noise in test assertions.

### Date comparison in tests uses pd.Timestamp, not datetime.date
DuckDB DATE columns come back from `.df()` as `numpy.datetime64` / `pd.Timestamp`
in pandas, not as `datetime.date`. Tests that filter rows by date value
(e.g. `df[df["week_start"] == date(2026, 5, 4)]`) silently return an empty
DataFrame when the left side is `Timestamp` and the right is `date`.
Fix: all date literals in tests use `pd.Timestamp("YYYY-MM-DD")`.
Fixture dates were chosen to land on ISO Mondays (2026-05-04, 2026-05-11) so
`DATE_TRUNC('week', posted_date)` returns the same date unchanged, making
expected values trivial to compute without a calendar lookup.
