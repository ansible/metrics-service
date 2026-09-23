"""Tests for the final anonymized Segment payload contract."""

from pydantic import ConfigDict, TypeAdapter, ValidationError, with_config

from apps.tasks.segment_types import FinalAnonymizedPayload

StrictPayload = with_config(ConfigDict(extra="forbid"))(FinalAnonymizedPayload)
payload_adapter = TypeAdapter(StrictPayload)


def valid_payload() -> dict:
    """Return a minimal structurally valid final payload."""
    return {
        "statistics": {
            "rollup_period_execution_environments_total": None,
            "rollup_period_EE_default_total": None,
            "rollup_period_EE_custom_total": None,
            "rollup_period_jobs_total": 0,
            "rollup_period_jobs_successful": 0,
            "rollup_period_jobs_failed": 0,
            "rollup_period_jobs_duration_all_statuses_seconds": 0,
            "rollup_period_jobs_successful_duration_total_seconds": 0,
            "rollup_period_jobs_failed_duration_total_seconds": 0,
            "rollup_period_organizations_total": 0,
            "rollup_period_forks_total": 0,
            "rollup_period_templates_total": 0,
            "rollup_period_inventories_total": 0,
            "rollup_period_unique_hosts_total": 0,
            "rollup_period_job_host_pairs_total": None,
            "rollup_period_successful_hosts_total": 0,
            "rollup_period_failed_hosts_total": 0,
            "rollup_period_unreachable_hosts_total": 0,
            "rollup_period_indirect_managed_nodes_all_total": 0,
            "rollup_period_tasks_total": 0,
            "rollup_period_task_ok_total": 0,
            "rollup_period_task_failed_total": 0,
            "rollup_period_task_skipped_total": 0,
            "rollup_period_task_unreachable_total": 0,
            "rollup_period_task_ignored_total": 0,
        },
        "rollup_period_ansible_versions": [],
        "rollup_period_scm_types": [],
        "rollup_period_credential_types": [],
        "jobs_by_job_type": [],
        "jobs_by_launch_type": [],
        "jobs_by_ansible_version": [],
        "jobs_by_controller_version": [],
        "jobs_by_installed_collections_versions": [],
        "table_metadata": {},
        "controller_versions": [],
        "feature_flags": [],
        "observability_by_tasks": [],
        "indirect_nodes_by_collection": [],
        "indirect_nodes_by_module": [],
        "summary_metadata": {
            "summary_date": "2026-09-22",
            "hourly_collections_count": 24,
            "missing_hours": [],
            "aggregation_timestamp": None,
            "install_type": "containerized",
        },
        "dashboard_telemetry": [
            {
                "task_name": "collect_dashboard_reports_initial_data",
                "success": True,
                "collection_duration_ms": 12.5,
                "number_of_records_processed": 10,
                "database_query_time_ms": None,
                "cache_hit_rate": None,
            }
        ],
    }


def test_valid_final_payload_passes_validation():
    """The utility payload plus service fields is accepted."""
    payload_adapter.validate_python(valid_payload(), strict=True)


def test_missing_required_utility_field_fails_validation():
    """Required fields inherited from metrics-utility remain enforced."""
    payload = valid_payload()
    del payload["statistics"]["rollup_period_jobs_total"]

    try:
        payload_adapter.validate_python(payload, strict=True)
    except ValidationError as error:
        assert "rollup_period_jobs_total" in str(error)
    else:
        raise AssertionError("Expected validation to fail")


def test_unknown_service_field_fails_validation():
    """Strict validation rejects fields outside the final contract."""
    payload = valid_payload()
    payload["unexpected"] = True

    try:
        payload_adapter.validate_python(payload, strict=True)
    except ValidationError as error:
        assert "unexpected" in str(error)
    else:
        raise AssertionError("Expected validation to fail")


def test_schema_contains_service_sections():
    """Generated schema exposes the service-owned payload sections."""
    schema = payload_adapter.json_schema(ref_template="#/components/schemas/{model}")

    assert "summary_metadata" in schema["properties"]
    assert "dashboard_telemetry" in schema["properties"]
