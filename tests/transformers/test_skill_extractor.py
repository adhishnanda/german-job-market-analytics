"""Tests for the skill extractor."""

from __future__ import annotations


from etl.transformers.skill_extractor import SKILL_MAP, extract_skills


class TestExtractSkillsBasic:
    def test_empty_string_returns_empty(self) -> None:
        assert extract_skills("") == []

    def test_whitespace_only_returns_empty(self) -> None:
        assert extract_skills("   \n\t  ") == []

    def test_no_skills_in_text_returns_empty(self) -> None:
        assert (
            extract_skills("Wir bieten ein tolles Team und flexible Arbeitszeiten.")
            == []
        )

    def test_single_skill_detected(self) -> None:
        assert extract_skills("We need strong Python experience.") == ["Python"]

    def test_multiple_skills_detected(self) -> None:
        skills = extract_skills("The role requires Python, SQL, and dbt.")
        assert "Python" in skills
        assert "SQL" in skills
        assert "dbt" in skills

    def test_returns_list(self) -> None:
        assert isinstance(extract_skills("Python developer"), list)

    def test_result_contains_only_strings(self) -> None:
        result = extract_skills("Python, SQL, Spark")
        assert all(isinstance(s, str) for s in result)


class TestExtractSkillsCaseInsensitive:
    def test_uppercase_matches(self) -> None:
        assert "Python" in extract_skills("PYTHON experience required")

    def test_mixed_case_matches(self) -> None:
        assert "dbt" in extract_skills("Experience with DBT is a plus")

    def test_canonical_name_returned_not_matched_case(self) -> None:
        # Canonical name is "Python" regardless of how it appears in text
        result = extract_skills("PYTHON and python and Python")
        assert result == ["Python"]


class TestExtractSkillsDeduplication:
    def test_skill_mentioned_twice_appears_once(self) -> None:
        result = extract_skills("Python is great. We use Python daily.")
        assert result.count("Python") == 1

    def test_alias_and_canonical_deduplicated(self) -> None:
        # "GCP" and "Google Cloud Platform" both → same canonical entry
        result = extract_skills("We use GCP and Google Cloud Platform.")
        assert result.count("Google Cloud Platform") == 1


class TestExtractSkillsWordBoundaries:
    def test_postgresql_does_not_match_bare_sql(self) -> None:
        result = extract_skills("We use PostgreSQL as our database.")
        assert "SQL" not in result
        assert "PostgreSQL" in result

    def test_python_not_matched_inside_longer_word(self) -> None:
        # "PythonScript" should not match Python
        assert extract_skills("PythonScript is not a real language.") == []

    def test_git_not_matched_in_github(self) -> None:
        result = extract_skills("We use GitHub Actions for CI.")
        assert "Git" not in result
        assert "GitHub Actions" in result

    def test_git_not_matched_in_gitlab(self) -> None:
        result = extract_skills("GitLab CI is our pipeline tool.")
        assert "Git" not in result
        assert "GitLab CI" in result

    def test_spark_matches_standalone(self) -> None:
        assert "Apache Spark" in extract_skills("Experience with Spark is required.")

    def test_spark_not_matched_in_sparkline(self) -> None:
        assert "Apache Spark" not in extract_skills("The sparkline chart looks great.")


class TestExtractSkillsAliases:
    def test_gcp_alias_resolves_to_canonical(self) -> None:
        result = extract_skills("Experience with GCP preferred.")
        assert "Google Cloud Platform" in result
        assert "GCP" not in result

    def test_azure_alias_resolves_to_canonical(self) -> None:
        result = extract_skills("Deployed on Azure.")
        assert "Microsoft Azure" in result

    def test_sklearn_alias_resolves_to_canonical(self) -> None:
        result = extract_skills("Familiar with sklearn pipelines.")
        assert "scikit-learn" in result

    def test_kafka_alias_resolves_to_canonical(self) -> None:
        result = extract_skills("Kafka experience is a plus.")
        assert "Apache Kafka" in result

    def test_airflow_alias_resolves_to_canonical(self) -> None:
        result = extract_skills("DAGs in Airflow.")
        assert "Apache Airflow" in result

    def test_postgres_alias_resolves_to_canonical(self) -> None:
        result = extract_skills("Postgres or MySQL.")
        assert "PostgreSQL" in result

    def test_k8s_alias_resolves_to_canonical(self) -> None:
        result = extract_skills("Kubernetes (k8s) orchestration.")
        assert "Kubernetes" in result
        assert result.count("Kubernetes") == 1

    def test_huggingface_alias_resolves_to_canonical(self) -> None:
        result = extract_skills("Using HuggingFace models.")
        assert "Hugging Face" in result


class TestExtractSkillsOrderStability:
    def test_same_input_returns_same_order(self) -> None:
        text = "Python, SQL, Spark, dbt, Docker"
        assert extract_skills(text) == extract_skills(text)

    def test_order_follows_skill_map_definition(self) -> None:
        # Python is defined before SQL in SKILL_MAP
        result = extract_skills("SQL and Python")
        python_idx = result.index("Python")
        sql_idx = result.index("SQL")
        assert python_idx < sql_idx


class TestSkillMapIntegrity:
    def test_all_skill_map_keys_are_strings(self) -> None:
        assert all(isinstance(k, str) for k in SKILL_MAP)

    def test_all_skill_map_values_are_lists_of_strings(self) -> None:
        for canonical, patterns in SKILL_MAP.items():
            assert isinstance(patterns, list), canonical
            assert all(isinstance(p, str) for p in patterns), canonical

    def test_no_empty_pattern_lists(self) -> None:
        assert all(len(patterns) > 0 for patterns in SKILL_MAP.values())
