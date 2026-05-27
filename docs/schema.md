# Data Schema

## `jobs_raw` — canonical table

Every extracted, normalised job posting lands here. The upsert key is `job_id`.
`jobs_clean` is a view over this table that filters to `is_duplicate = false`.

### Identity and provenance

| Field | Type | Source | Description | Example |
|---|---|---|---|---|
| `job_id` | VARCHAR PK | All extractors | Source-prefixed unique ID | `BA_10000-1183204759-S` |
| `source` | VARCHAR | Normalizer | Source name | `bundesagentur` |
| `source_keyword` | VARCHAR | Extractors | Search keyword that returned this record | `Data Engineer` |
| `source_city` | VARCHAR | Extractors | Search city used | `Berlin` |
| `snapshot_date` | DATE | Extractors | Date of the raw snapshot file | `2026-05-28` |
| `fetched_at` | TIMESTAMP | Normalizer | UTC timestamp of extraction | `2026-05-28T09:14:22Z` |
| `url` | VARCHAR | All | Direct URL to the job posting | `https://www.stepstone.de/job/...` |

### Raw text fields (immutable after extraction)

| Field | Type | Source | Description | Example |
|---|---|---|---|---|
| `title_raw` | VARCHAR | All | Job title exactly as returned by source | `Senior Data Engineer (w/m/d)` |
| `description_raw` | TEXT | All | Full description text, unmodified | `Wir suchen einen...` |
| `salary_raw` | VARCHAR | All | Raw salary string from source, if present | `€60.000 – €80.000 p.a.` |

### Normalised job attributes

| Field | Type | Source | Description | Example |
|---|---|---|---|---|
| `title_normalized` | VARCHAR | Normalizer | Cleaned, lowercased title for grouping | `data engineer` |
| `company` | VARCHAR | All | Employer name | `Zalando SE` |
| `city` | VARCHAR | All | City of the role | `Berlin` |
| `region` | VARCHAR | BA / Normalizer | German federal state | `BERLIN` |
| `country` | VARCHAR | Normalizer | Always `DE` for this dataset | `DE` |
| `postal_code` | VARCHAR | BA | Postal code of the role address | `10247` |
| `lat` | DOUBLE | BA | Latitude (from `stellenlokationen`) | `52.5145` |
| `lon` | DOUBLE | BA | Longitude (from `stellenlokationen`) | `13.4655` |
| `posted_date` | DATE | All | Date the job was first published | `2026-05-11` |
| `employment_type` | VARCHAR | All | Contract type | `FULL_TIME` \| `PART_TIME` \| `CONTRACT` \| `INTERNSHIP` \| `UNKNOWN` |
| `work_model` | VARCHAR | All | Remote policy | `ONSITE` \| `REMOTE` \| `HYBRID` \| `UNKNOWN` |
| `language` | VARCHAR | langdetect | Detected language of `description_raw` | `de` \| `en` |
| `role_category` | VARCHAR | Normalizer | Classified role bucket (see taxonomy below) | `Data Engineering` |

### Parsed salary

| Field | Type | Source | Description | Example |
|---|---|---|---|---|
| `salary_min` | DOUBLE | salary_parser | Minimum salary, EUR per year | `60000.0` |
| `salary_max` | DOUBLE | salary_parser | Maximum salary, EUR per year | `80000.0` |
| `salary_currency` | VARCHAR | salary_parser | Currency code | `EUR` |

All three fields are `NULL` when no salary information is present.
Monthly figures are converted to annual (`× 12`) during parsing.

### Skill extraction

| Field | Type | Source | Description | Example |
|---|---|---|---|---|
| `skills` | VARCHAR[] | skill_extractor | Deduplicated list of tech skills found in `description_raw` | `['Python', 'Spark', 'dbt']` |

Stored as a DuckDB `VARCHAR[]` array. Empty array `[]` when no recognised
skills are found.

### Deduplication

| Field | Type | Source | Description | Example |
|---|---|---|---|---|
| `is_duplicate` | BOOLEAN | deduplicator | `true` if a canonical record exists | `false` |
| `canonical_id` | VARCHAR | deduplicator | `job_id` of the canonical record; `NULL` if this record is canonical | `BA_10000-abc` |

---

## Source-to-canonical field mapping

| Canonical field | Bundesagentur (v6) | Indeed RSS | Stepstone HTML | LinkedIn CSV |
|---|---|---|---|---|
| `job_id` | `BA_{referenznummer}` | `IN_{guid}` | `SS_{internal_id}` | `LI_{li_id}` |
| `title_raw` | `stellenangebotsTitel` | `title` | scraped `h1.job-title` | `title` column |
| `company` | `firma` | `author` | scraped `.company-name` | `company` column |
| `city` | `stellenlokationen[0].adresse.ort` | parsed from `location` | scraped `.location` | `location` column |
| `postal_code` | `stellenlokationen[0].adresse.plz` | — | — | — |
| `lat` | `stellenlokationen[0].breite` | — | — | — |
| `lon` | `stellenlokationen[0].laenge` | — | — | — |
| `posted_date` | `veroeffentlichungszeitraum.von` | `published` | scraped date attr | `posted_date` column |
| `url` | constructed from `referenznummer` | `link` | scraped `<a>` href | `url` column |
| `description_raw` | from detail endpoint call | `summary` | scraped description div | `description` column |
| `work_model` | `homeofficetyp` mapping | keyword scan | keyword scan | `remote` column |

---

## Role category taxonomy

The `role_category` field is assigned by the normaliser using keyword matching
on `title_normalized`. Precedence is top-to-bottom.

| Category | Title keywords matched |
|---|---|
| `Data Engineering` | data engineer, etl, pipeline, data platform, data infrastructure |
| `Analytics Engineering` | analytics engineer, dbt, data modelling, data modeling |
| `Data Science / ML` | data scientist, machine learning, ml engineer, deep learning, nlp, computer vision |
| `Data Analysis / BI` | data analyst, business intelligence, bi developer, reporting, power bi, tableau |
| `ML Engineering` | ml engineer, mlops, model deployment, feature engineering |
| `Data Architect` | data architect, data mesh, lakehouse |
| `Other` | anything that matches none of the above |

---

## Skill extraction dictionary

Skill matching uses case-insensitive whole-word regex against `description_raw`.
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
| `UNKNOWN` | field absent | no recognisable keyword |

## Work model mapping

| Canonical value | Bundesagentur `homeofficetyp` | Text keyword signals |
|---|---|---|
| `REMOTE` | `VOLLSTAENDIG_IM_HOMEOFFICE` | "remote", "fully remote", "100% remote" |
| `HYBRID` | `NACH_VEREINBARUNG` | "hybrid", "teilweise remote", "flex" |
| `ONSITE` | `KEIN_HOMEOFFICE` | "before-office", "vor Ort" or no remote mention |
| `UNKNOWN` | field absent | no recognisable keyword |
