"""Verify the job_market_pipeline DAG loads and has the expected structure.

Path note: the local airflow/ directory (the DAGs folder) shadows the installed
apache-airflow package when the project root is first on sys.path.  Re-ordering
sys.path here — before any airflow import — ensures the installed package is found.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = str(Path(__file__).parent.parent.resolve())
sys.path = [p for p in sys.path if p not in (_ROOT, "")] + [_ROOT]

# Load the DAG module by absolute path to avoid the airflow/ namespace conflict.
_dag_path = Path(__file__).parent.parent / "airflow" / "dags" / "job_market_pipeline.py"
_spec = importlib.util.spec_from_file_location("_job_market_pipeline_dag", _dag_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)  # type: ignore[union-attr]
dag = _module.dag


def test_dag_imports_without_error() -> None:
    """DAG object is a proper Airflow DAG instance."""
    from airflow import DAG

    assert isinstance(dag, DAG)


def test_dag_id() -> None:
    assert dag.dag_id == "job_market_pipeline"


def test_dag_schedule() -> None:
    assert dag.schedule == "@daily"


def test_dag_catchup_is_false() -> None:
    assert dag.catchup is False


def test_dag_has_exactly_six_tasks() -> None:
    expected = {
        "extract_ba",
        "extract_ss",
        "sensor_li",
        "extract_li",
        "deduplicate_all",
        "load_to_duckdb",
    }
    assert set(dag.task_ids) == expected


def test_extract_ba_is_root() -> None:
    """extract_ba has no upstream dependencies."""
    assert dag.task_dict["extract_ba"].upstream_task_ids == set()


def test_extract_ss_is_root() -> None:
    """extract_ss has no upstream dependencies."""
    assert dag.task_dict["extract_ss"].upstream_task_ids == set()


def test_deduplicate_all_upstream() -> None:
    """deduplicate_all waits for all three extract tasks."""
    assert dag.task_dict["deduplicate_all"].upstream_task_ids == {
        "extract_ba",
        "extract_ss",
        "extract_li",
    }


def test_load_to_duckdb_upstream() -> None:
    """load_to_duckdb depends only on deduplicate_all."""
    assert dag.task_dict["load_to_duckdb"].upstream_task_ids == {"deduplicate_all"}
