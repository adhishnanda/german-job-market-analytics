# Data Schema

## `jobs_raw` — canonical table

Every extracted, normalised job posting lands here. The upsert key is `job_id`.
`jobs_clean` and `skills_exploded` are views over this table (see below).

Column count: 29. Table format below: **Field | Type | Source | Nullable | Notes**.

### Identity and provenance

| Field | Type | Source | Nullable | Notes |
|---|---|---|---|---|
| `job_id` | VARCHAR PK | All extractors | NOT NULL | Source-prefixed unique ID: `BA_*`, `IN_*`, `SS_*`, `LI_*` |
| `source` | VARCHAR | Normalizer | NOT NULL | One of `bundesagentur`, `indeed`, `stepstone`, `linkedin` |
| `source_keyword` | VARCHAR | Extractors | NOT NULL | Search keyword that returned this record |
| `source_city` | VARCHAR | Extractors | NOT NULL | Search city used for this query |
| `snapshot_date` | DATE | Extractors | NOT NULL | Date of the raw snapshot directory (`YYYY-MM-DD`) |
| `fetched_at` | TIMESTAMP | Normalizer | NOT NULL | UTC timestamp of extraction |
| `url` | VARCHAR | All | nullable | Constructed from `referenznummer` for BA; scraped for SS; from RSS link for IN; from CSV for LI |

> **BA URL pattern:** `https://www.arbeitsagentur.de/jobsuche/jobdetail/{referenznummer}` — constructed by the normalizer; `NULL` if `referenznummer` is absent.

### Raw text fields (immutable after extraction)

| Field | Type | Source | Nullable | Notes |
|---|---|---|---|---|
| `title_raw` | VARCHAR | All | NOT NULL | Job title exactly as returned by source; never modified after extraction |
| `description_raw` | TEXT | All | NOT NULL | Full description text, unmodified. Defaults to `""` for BA (search-list records) and SS (search-result cards); no detail page is fetched for either |
| `salary_raw` | VARCHAR | All | nullable | Raw salary string from source, if present. `NULL` when source provides no salary text |

### Normalised job attributes

| Field | Type | Source | Nullable | Notes |
|---|---|---|---|---|
| `title_normalized` | VARCHAR | Normalizer | NOT NULL | `.lower().strip()` of `title_raw`; used for role taxonomy matching and display grouping |
| `company` | VARCHAR | All | nullable | Employer name; may be absent in some BA records |
| `city` | VARCHAR | All | nullable | City of the role; `NULL` if not parseable from source |
| `region` | VARCHAR | BA / Normalizer | nullable | German federal state (e.g. `BERLIN`); `NULL` for all non-BA sources |
| `country` | VARCHAR | Normalizer | NOT NULL | Always `DE` for this dataset |
| `postal_code` | VARCHAR | BA | nullable | Postal code of the role address; `NULL` for all non-BA sources |
| `lat` | DOUBLE | BA | nullable | Latitude from `stellenlokationen`; `NULL` for all non-BA sources |
| `lon` | DOUBLE | BA | nullable | Longitude from `stellenlokationen`; `NULL` for all non-BA sources |
| `posted_date` | DATE | All | nullable | Date the job was first published; ~8% null for Stepstone; ±2-day approximate for LinkedIn |
| `employment_type` | VARCHAR | All | NOT NULL | Default `"UNKNOWN"`. BA derives from `arbeitszeitVollzeit` (structured); others use regex on description text. Values: `FULL_TIME`, `PART_TIME`, `CONTRACT`, `INTERNSHIP`, `UNKNOWN` |
| `work_model` | VARCHAR | All | NOT NULL | Default `"UNKNOWN"`. BA derives from `homeofficetyp` (structured); others use keyword scan. Values: `ONSITE`, `REMOTE`, `HYBRID`, `UNKNOWN` |
| `language` | VARCHAR | langdetect | NOT NULL | Default `"unknown"` — `langdetect` raises on short or empty `description_raw`. Values: `de`, `en`, `unknown`, and other ISO 639-1 codes |
| `role_category` | VARCHAR | Normalizer | NOT NULL | Default `"Other"` when no keyword in the taxonomy matches `title_normalized`. See taxonomy below |

### Parsed salary

| Field | Type | Source | Nullable | Notes |
|---|---|---|---|---|
| `salary_min` | DOUBLE | salary_parser | nullable | Minimum salary in EUR per year. `NULL` when no salary text is present |
| `salary_max` | DOUBLE | salary_parser | nullable | Maximum salary in EUR per year. `NULL` when no salary text is present. Equals `salary_min` when only a single figure is found |
| `salary_currency` | VARCHAR | salary_parser | nullable | Currency code (always `EUR` when populated). `NULL` together with the two salary fields |

Monthly figures are converted to annual (`× 12`) during parsing. All three fields are `NULL` together; they are never partially populated.

### Skill extraction

| Field | Type | Source | Nullable | Notes |
|---|---|---|---|---|
| `skills` | VARCHAR[] | skill_extractor | NOT NULL | Deduplicated list of recognised tech skills found in `description_raw`. Default `[]` (empty array) when no recognised skills are found or when `description_raw` is empty |

Stored as a DuckDB `VARCHAR[]` array. The normalizer initializes `skills` as `[]`; the pipeline runner calls `skill_extractor.extract_skills(description_raw)` and writes the result back. The two steps are decoupled so the skill dictionary can be updated without re-running the full normalizer.

### Deduplication

| Field | Type | Source | Nullable | Notes |
|---|---|---|---|---|
| `is_duplicate` | BOOLEAN | deduplicator | NOT NULL | `TRUE` if a higher-priority canonical record covers this posting |
| `canonical_id` | VARCHAR | deduplicator | nullable | `job_id` of the canonical record. `NULL` when this record is itself canonical |

---

## Views

### `jobs_clean`

```sql
CREATE VIEW jobs_clean AS
SELECT * FROM jobs_raw WHERE is_duplicate = FALSE;
```

All 29 columns of `jobs_raw`, filtered to canonical records only. Use this view for all analytics queries — never query `jobs_raw` directly for analysis.

### `skills_exploded`

```sql
CREATE VIEW skills_exploded AS
SELECT job_id, source, posted_date, UNNEST(skills) AS skill
FROM jobs_raw WHERE is_duplicate = FALSE;
```

One row per (job, skill) pair for all canonical records. The `UNNEST` flattens the `VARCHAR[]` array. Jobs with `skills = []` produce no rows in this view. Used by `skill_demand_weekly` and any per-skill aggregation.

---

## Source-to-canonical field mapping

| Canonical field | Bundesagentur (v6) | Indeed RSS | Stepstone HTML | LinkedIn CSV |
|---|---|---|---|---|
| `job_id` | `BA_{referenznummer}` | `IN_{guid}` | `SS_{internal_id}` | `LI_{li_id}` |
| `title_raw` | `stellenangebotsTitel` | `title` | scraped job title | `title` column |
| `company` | `firma` | `author` | scraped company span | `company` column |
| `city` | `stellenlokationen[0].adresse.ort` | parsed from `location` | scraped location | `location` column; default `"Berlin"` |
| `postal_code` | `stellenlokationen[0].adresse.plz` | — | — | — |
| `lat` | `stellenlokationen[0].breite` | — | — | — |
| `lon` | `stellenlokationen[0].laenge` | — | — | — |
| `posted_date` | `veroeffentlichungszeitraum.von` | `published` (RFC 2822) | German relative string | relative string or ISO |
| `url` | constructed from `referenznummer` | `link` | scraped `<a>` href | `url` column |
| `description_raw` | `""` (search list only) | `summary` | `""` (cards only) | `description` column |
| `employment_type` | `arbeitszeitVollzeit` mapping | keyword scan | keyword scan | `employment_type` column |
| `work_model` | `homeofficetyp` mapping | keyword scan | keyword scan | `is_remote` column |

---

## Role category taxonomy

The `role_category` field is assigned by the normaliser using keyword matching
on `title_normalized`. Precedence is top-to-bottom; first match wins; falls
through to `"Other"` when nothing matches.

| Category | Title keywords matched |
|---|---|
| `Data Engineering` | data engineer, etl, pipeline, data platform, data infrastructure |
| `Analytics Engineering` | analytics engineer, dbt, data modelling, data modeling |
| `Data Science / ML` | data scientist, machine learning, ml engineer, deep learning, nlp, computer vision |
| `Data Analysis / BI` | data analyst, business intelligence, bi developer, reporting, power bi, tableau |
| `ML Engineering` | ml engineer, mlops, model deployment, feature engineering |
| `Data Architect` | data architect, data mesh, lakehouse |
| `Other` | anything that matches none of the above (the default) |

---

## Skill extraction dictionary

Skill matching uses case-insensitive whole-word regex (`\b`) against `description_raw`.
Aliases are collapsed to the canonical form shown below.

### Query and processing languages
`Python`, `SQL`, `Scala`, `R`, `Java`, `Bash`, `Julia`

### Data engineering tools
`Apache Spark`, `Apache Kafka`, `Apache Flink`, `dbt`, `Apache Airflow`,
`Prefect`, `Dagster`, `Luigi`, `Apache Beam`

### Storage and databases
`DuckDB`, `PostgreSQL`, `MySQL`, `SQLite`, `MongoDB`, `Elasticsearch`,
`Redis`, `Cassandra`, `ClickHouse`

### Cloud data warehouses and lakes
`BigQuery`, `Amazon Redshift`, `Snowflake`, `Azure Synapse`, `Databricks`,
`Delta Lake`, `Apache Iceberg`, `Apache Hudi`, `Amazon S3`, `Azure Data Lake`

### Cloud platforms
`AWS`, `Google Cloud Platform` (aliases: `GCP`), `Microsoft Azure` (aliases: `Azure`)

### ML and data science libraries
`scikit-learn`, `TensorFlow`, `PyTorch`, `Keras`, `XGBoost`, `LightGBM`,
`Hugging Face`, `MLflow`, `Kubeflow`, `Ray`

### Visualisation and BI
`Power BI`, `Tableau`, `Looker`, `Streamlit`, `Grafana`, `Apache Superset`,
`Metabase`, `Plotly`, `Altair`

### Containers and DevOps
`Docker`, `Kubernetes`, `Terraform`, `Ansible`, `Git`, `GitHub Actions`,
`GitLab CI`, `Jenkins`

### Data formats and protocols
`Parquet`, `Avro`, `JSON`, `CSV`, `Protobuf`, `YAML`, `REST API`, `GraphQL`,
`gRPC`

---

## Employment type mapping

| Canonical value | Bundesagentur `arbeitszeitVollzeit` | Indeed / Stepstone / LinkedIn text |
|---|---|---|
| `FULL_TIME` | `true` | "full-time", "Vollzeit" |
| `PART_TIME` | `false` (and no other indicator) | "part-time", "Teilzeit" |
| `CONTRACT` | n/a | "freelance", "contract", "befristet" |
| `INTERNSHIP` | n/a | "intern", "Praktikum", "Werkstudent" |
| `UNKNOWN` | field absent | no recognisable keyword; **the default** |

## Work model mapping

| Canonical value | Bundesagentur `homeofficetyp` | Text keyword signals |
|---|---|---|
| `REMOTE` | `VOLLSTAENDIG_IM_HOMEOFFICE` | "remote", "fully remote", "100% remote" |
| `HYBRID` | `NACH_VEREINBARUNG` | "hybrid", "teilweise remote", "flex"; also LinkedIn `is_remote=True` |
| `ONSITE` | `KEIN_HOMEOFFICE` | "vor Ort" or no remote mention |
| `UNKNOWN` | field absent | no recognisable keyword; **the default** |
