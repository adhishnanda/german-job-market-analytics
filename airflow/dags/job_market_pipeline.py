"""Airflow DAG: orchestrates the full German job-market ETL pipeline."""
from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

with DAG(
    dag_id="job_market_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["gjma"],
) as dag:
    # Tasks will be added as extractors are implemented.
    pass
