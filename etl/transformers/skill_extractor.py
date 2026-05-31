"""Extract tech-skill mentions from job description text."""

from __future__ import annotations

import re

# Canonical skill name → regex patterns matched case-insensitively.
# Aliases (e.g. GCP → Google Cloud Platform) are handled by listing
# multiple patterns under the canonical key.
SKILL_MAP: dict[str, list[str]] = {
    # Query and processing languages
    "Python": [r"\bPython\b"],
    "SQL": [r"\bSQL\b"],
    "Scala": [r"\bScala\b"],
    "R": [r"\bR\b"],
    "Java": [r"\bJava\b"],
    "Bash": [r"\bBash\b"],
    "Julia": [r"\bJulia\b"],
    # Data engineering tools
    "Apache Spark": [r"\bApache Spark\b", r"\bSpark\b"],
    "Apache Kafka": [r"\bApache Kafka\b", r"\bKafka\b"],
    "Apache Flink": [r"\bApache Flink\b", r"\bFlink\b"],
    "dbt": [r"\bdbt\b"],
    "Apache Airflow": [r"\bApache Airflow\b", r"\bAirflow\b"],
    "Prefect": [r"\bPrefect\b"],
    "Dagster": [r"\bDagster\b"],
    "Luigi": [r"\bLuigi\b"],
    "Apache Beam": [r"\bApache Beam\b", r"\bBeam\b"],
    # Storage and databases
    "DuckDB": [r"\bDuckDB\b"],
    "PostgreSQL": [r"\bPostgreSQL\b", r"\bPostgres\b"],
    "MySQL": [r"\bMySQL\b"],
    "SQLite": [r"\bSQLite\b"],
    "MongoDB": [r"\bMongoDB\b"],
    "Elasticsearch": [r"\bElasticsearch\b"],
    "Redis": [r"\bRedis\b"],
    "Cassandra": [r"\bCassandra\b"],
    "ClickHouse": [r"\bClickHouse\b"],
    # Cloud data warehouses and lakes
    "BigQuery": [r"\bBigQuery\b"],
    "Amazon Redshift": [r"\bAmazon Redshift\b", r"\bRedshift\b"],
    "Snowflake": [r"\bSnowflake\b"],
    "Azure Synapse": [r"\bAzure Synapse\b"],
    "Databricks": [r"\bDatabricks\b"],
    "Delta Lake": [r"\bDelta Lake\b"],
    "Apache Iceberg": [r"\bApache Iceberg\b", r"\bIceberg\b"],
    "Apache Hudi": [r"\bApache Hudi\b", r"\bHudi\b"],
    "Amazon S3": [r"\bAmazon S3\b", r"\bS3\b"],
    "Azure Data Lake": [r"\bAzure Data Lake\b"],
    # Cloud platforms
    "AWS": [r"\bAWS\b"],
    "Google Cloud Platform": [r"\bGoogle Cloud Platform\b", r"\bGCP\b"],
    "Microsoft Azure": [r"\bMicrosoft Azure\b", r"\bAzure\b"],
    # ML and data science libraries
    "scikit-learn": [r"\bscikit-learn\b", r"\bsklearn\b"],
    "TensorFlow": [r"\bTensorFlow\b"],
    "PyTorch": [r"\bPyTorch\b"],
    "Keras": [r"\bKeras\b"],
    "XGBoost": [r"\bXGBoost\b"],
    "LightGBM": [r"\bLightGBM\b"],
    "Hugging Face": [r"\bHugging Face\b", r"\bHuggingFace\b"],
    "MLflow": [r"\bMLflow\b"],
    "Kubeflow": [r"\bKubeflow\b"],
    "Ray": [r"\bRay\b"],
    # Visualisation and BI
    "Power BI": [r"\bPower BI\b"],
    "Tableau": [r"\bTableau\b"],
    "Looker": [r"\bLooker\b"],
    "Streamlit": [r"\bStreamlit\b"],
    "Grafana": [r"\bGrafana\b"],
    "Apache Superset": [r"\bApache Superset\b", r"\bSuperset\b"],
    "Metabase": [r"\bMetabase\b"],
    "Plotly": [r"\bPlotly\b"],
    "Altair": [r"\bAltair\b"],
    # Containers and DevOps
    "Docker": [r"\bDocker\b"],
    "Kubernetes": [r"\bKubernetes\b", r"\bk8s\b"],
    "Terraform": [r"\bTerraform\b"],
    "Ansible": [r"\bAnsible\b"],
    "Git": [r"\bGit\b"],
    "GitHub Actions": [r"\bGitHub Actions\b"],
    "GitLab CI": [r"\bGitLab CI\b"],
    "Jenkins": [r"\bJenkins\b"],
    # Data formats and protocols
    "Parquet": [r"\bParquet\b"],
    "Avro": [r"\bAvro\b"],
    "JSON": [r"\bJSON\b"],
    "CSV": [r"\bCSV\b"],
    "Protobuf": [r"\bProtobuf\b", r"\bProtocol Buffers\b"],
    "YAML": [r"\bYAML\b"],
    "REST API": [r"\bREST API\b", r"\bRESTful API\b"],
    "GraphQL": [r"\bGraphQL\b"],
    "gRPC": [r"\bgRPC\b"],
}

# Compiled once at module load — (canonical_name, combined_pattern) pairs
_COMPILED: list[tuple[str, re.Pattern[str]]] = [
    (canonical, re.compile("|".join(patterns), re.IGNORECASE))
    for canonical, patterns in SKILL_MAP.items()
]


def extract_skills(description: str) -> list[str]:
    """Return a deduplicated list of recognised skills found in *description*."""
    if not description or not description.strip():
        return []
    # dict preserves insertion order and deduplicates by key
    matched: dict[str, None] = {}
    for canonical, pattern in _COMPILED:
        if pattern.search(description):
            matched[canonical] = None
    return list(matched)
