"""Airflow DAG: orchestrates the full German job-market ETL pipeline."""

from __future__ import annotations

import logging
from typing import Any

import pendulum
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.sensors.filesystem import FileSensor

logger = logging.getLogger(__name__)


def _extract_ba(**context: Any) -> None:
    """Run the Bundesagentur extractor and push raw records to XCom."""
    from etl.extractors.bundesagentur import extract

    records: list[dict[str, Any]] = extract()
    context["ti"].xcom_push(key="ba_records", value=records)


def _extract_ss(**context: Any) -> None:
    """Run the Stepstone extractor and push raw records to XCom."""
    from etl.extractors.stepstone import fetch_jobs

    records: list[dict[str, Any]] = fetch_jobs()
    context["ti"].xcom_push(key="ss_records", value=records)


def _extract_li(**context: Any) -> None:
    """Read the LinkedIn CSV for the run date and push records to XCom.

    Pushes [] when the sensor soft-failed (no CSV placed for this run date).
    """
    from etl.extractors.linkedin import read_csvs

    ds: str = context["ds"]
    try:
        records: list[dict[str, Any]] = read_csvs(date_str=ds)
    except Exception:
        logger.warning("LinkedIn CSV read failed for %s — using []", ds)
        records = []
    context["ti"].xcom_push(key="li_records", value=records)


def _deduplicate_all(**context: Any) -> None:
    """Pull extract XComs, normalise, extract skills, deduplicate, push result."""
    from etl.transformers.deduplicator import deduplicate
    from etl.transformers.normalizer import normalize
    from etl.transformers.skill_extractor import extract_skills

    ti = context["ti"]
    ba_records: list[dict[str, Any]] = (
        ti.xcom_pull(task_ids="extract_ba", key="ba_records") or []
    )
    ss_records: list[dict[str, Any]] = (
        ti.xcom_pull(task_ids="extract_ss", key="ss_records") or []
    )
    li_records: list[dict[str, Any]] = (
        ti.xcom_pull(task_ids="extract_li", key="li_records") or []
    )

    all_normalized: list[dict[str, Any]] = []
    for source, batch in (
        ("bundesagentur", ba_records),
        ("stepstone", ss_records),
        ("linkedin", li_records),
    ):
        for raw in batch:
            canonical = normalize(raw, source)
            canonical["skills"] = extract_skills(canonical.get("description_raw") or "")
            all_normalized.append(canonical)

    deduped: list[dict[str, Any]] = deduplicate(all_normalized)
    ti.xcom_push(key="deduped_records", value=deduped)


def _load_to_duckdb(**context: Any) -> None:
    """Pull deduped records from XCom and upsert into DuckDB."""
    import duckdb
    from etl.loaders.duckdb_loader import load_to_connection

    ti = context["ti"]
    records: list[dict[str, Any]] = (
        ti.xcom_pull(task_ids="deduplicate_all", key="deduped_records") or []
    )
    conn = duckdb.connect("data/db/jobs.duckdb")
    try:
        load_to_connection(records, conn)
    finally:
        conn.close()


with DAG(
    dag_id="job_market_pipeline",
    start_date=pendulum.now("UTC").subtract(days=1),
    schedule="@daily",
    catchup=False,
    tags=["gjma"],
) as dag:
    extract_ba = PythonOperator(
        task_id="extract_ba",
        python_callable=_extract_ba,
    )

    extract_ss = PythonOperator(
        task_id="extract_ss",
        python_callable=_extract_ss,
    )

    sensor_li = FileSensor(
        task_id="sensor_li",
        filepath="data/raw/linkedin/{{ ds }}/",
        poke_interval=300,
        timeout=3600,
        mode="poke",
        soft_fail=True,
    )

    extract_li = PythonOperator(
        task_id="extract_li",
        python_callable=_extract_li,
    )

    deduplicate_all = PythonOperator(
        task_id="deduplicate_all",
        python_callable=_deduplicate_all,
    )

    load_to_duckdb = PythonOperator(
        task_id="load_to_duckdb",
        python_callable=_load_to_duckdb,
    )

    sensor_li >> extract_li
    [extract_ba, extract_ss, extract_li] >> deduplicate_all >> load_to_duckdb
