"""Unit tests for support-bundle collectors."""

import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.analytics.models import AnalyticsPayload
from apps.core.support_bundle import collectors
from apps.tasks.models import (
    AnonymizedMetricsPayload,
    DailyMetricsSummary,
    HourlyMetricsCollection,
    Task,
    TaskExecution,
)

pytestmark = pytest.mark.unit


class FakeControl:
    """Minimal dispatcherd control double."""

    def __init__(self, replies):
        self.replies = replies

    def control_with_reply(self, command, expected_replies=1, timeout=1.0, data=None):
        return self.replies.get(command, [])


@pytest.mark.django_db
def test_collect_tasks_marks_stuck_run_and_merges_dispatcherd():
    now = timezone.now()
    stuck = Task.objects.create(
        name="stuck-task",
        function_name="hello_world",
        status="running",
        started_at=now - timedelta(seconds=collectors.DEFAULT_TASK_TIMEOUT + 60),
    )
    pending = Task.objects.create(name="pending-task", function_name="hello_world", status="pending")
    TaskExecution.objects.create(task=stuck, status="running", worker_id="worker-7")

    replies = {
        "running": [{"worker-7": {"task": "hello_world", "uuid": "uuid-7"}, "node_id": "node-1"}],
        "workers": [{"worker-7": {"status": "running"}, "node_id": "node-1"}],
    }
    with (
        patch.object(collectors, "ensure_dispatcherd_configured"),
        patch.object(collectors, "get_control_from_settings", return_value=FakeControl(replies)),
    ):
        result = collectors.collect_tasks()

    rows = {row["task_id"]: row for row in result["tasks"]}
    assert result["dispatcherd"]["available"] is True
    assert rows[stuck.pk]["stuck"] is True
    assert rows[stuck.pk]["duration_seconds"] > collectors.DEFAULT_TASK_TIMEOUT
    assert rows[stuck.pk]["worker_id"] == "worker-7"
    assert rows[stuck.pk]["current_task_uuid"] == "uuid-7"
    assert rows[pending.pk]["stuck"] is False
    assert result["stuck_task_ids"] == [stuck.pk]


@pytest.mark.django_db
def test_collect_tasks_falls_back_to_db_when_dispatcherd_fails():
    task = Task.objects.create(name="pending", function_name="hello_world", status="pending")

    with patch.object(collectors, "ensure_dispatcherd_configured", side_effect=RuntimeError("broker down")):
        result = collectors.collect_tasks()

    assert result["dispatcherd"]["available"] is False
    assert "broker down" in result["dispatcherd"]["error"]
    assert [row["task_id"] for row in result["tasks"]] == [task.pk]


@pytest.mark.django_db
def test_collect_ingestion_builds_per_collector_history_without_payloads():
    now = timezone.now()
    HourlyMetricsCollection.objects.create(
        collector_type="unified_jobs",
        collection_timestamp=now - timedelta(hours=3),
        status="collected",
    )
    HourlyMetricsCollection.objects.create(
        collector_type="unified_jobs",
        collection_timestamp=now - timedelta(hours=2),
        status="failed",
        error_message="first failure",
    )
    HourlyMetricsCollection.objects.create(
        collector_type="unified_jobs",
        collection_timestamp=now - timedelta(hours=1),
        status="failed",
        error_message="latest failure",
    )
    summary = DailyMetricsSummary.objects.create(
        summary_date=timezone.now().date(),
        status="aggregated",
        hourly_collections_count=3,
        missing_hours=["0", "1"],
    )
    AnonymizedMetricsPayload.objects.create(
        summary_date=summary.summary_date,
        anonymized_data={"leak": "should-not-appear"},
        status="failed",
        retry_count=2,
        error_message="segment down",
    )
    AnalyticsPayload.objects.create(
        collector="unified_jobs",
        source="local",
        cluster_id="cluster-abc",
        started_at=now - timedelta(minutes=2),
        finished_at=now - timedelta(minutes=1),
    )

    result = collectors.collect_ingestion()

    collector_state = result["collectors"][0]
    assert collector_state["collector_type"] == "unified_jobs"
    assert collector_state["consecutive_failures"] == 2
    assert collector_state["last_error_message"] == "latest failure"
    assert collector_state["last_failure_at"] is not None
    assert collector_state["last_success_at"] is not None
    assert result["daily_summaries"][0]["missing_hours_count"] == 2
    assert result["segment"][0]["retry_count"] == 2
    assert result["analytics_payloads"][0]["cluster_id"] == "cluster-abc"
    assert "should-not-appear" not in json.dumps(result)
    assert result["dimension"] == "collector"


@pytest.mark.django_db
def test_collect_queues_counts_pending_rows_per_queue():
    Task.objects.create(name="maintenance", function_name="hello_world", status="pending")
    Task.objects.create(name="metrics-1", function_name="collect_hourly_metrics", status="pending")
    Task.objects.create(name="completed", function_name="collect_hourly_metrics", status="completed")

    replies = {
        "running": [{"queued-0": {"task": "hello_world"}, "blocked-0": {}, "node_id": "node-1"}],
        "workers": [{"worker-1": {"status": "idle"}, "node_id": "node-1"}],
        "producers": [{"brokered": {"status": "running"}, "node_id": "node-1"}],
    }
    with (
        patch.object(collectors, "ensure_dispatcherd_configured"),
        patch.object(collectors, "get_control_from_settings", return_value=FakeControl(replies)),
    ):
        result = collectors.collect_queues()

    by_name = {queue["name"]: queue["db_pending"] for queue in result["queues"]}
    assert by_name["maintenance"] == 1
    assert by_name["metrics"] == 1
    assert by_name["dashboard"] == 0
    assert result["db_pending_total"] == 2
    assert result["live_available"] is True
    assert result["dispatcherd"]["queued"] == 1
    assert result["dispatcherd"]["blocked"] == 1


@pytest.mark.django_db
def test_collect_queues_falls_back_when_dispatcherd_fails():
    with patch.object(collectors, "ensure_dispatcherd_configured", side_effect=RuntimeError("no broker")):
        result = collectors.collect_queues()

    assert result["live_available"] is False
    assert result["dispatcherd"]["available"] is False
    assert {queue["name"] for queue in result["queues"]} >= {"dashboard", "maintenance", "metrics"}


@pytest.mark.django_db
def test_collect_schema_reports_migrations():
    result = collectors.collect_schema()

    assert result["connected"] is True
    assert result["vendor"] == "postgresql"
    assert result["database"]["name"]
    assert isinstance(result["applied_migrations"], list)
    assert isinstance(result["unapplied_migrations"], list)
    assert result["django_version"]


def test_collect_schema_survives_database_error():
    broken_connection = Mock()
    broken_connection.ensure_connection.side_effect = RuntimeError("connection refused")

    with patch.object(collectors, "connection", broken_connection):
        result = collectors.collect_schema()

    assert result["connected"] is False
    assert "connection refused" in result["error"]
    assert result["django_version"]


def test_collect_settings_never_contains_secret_values():
    dynaconf = Mock()
    dynaconf.as_dict.return_value = {
        "SECRET_KEY": "test-secret-key-value",
        "SEGMENT_WRITE_KEY": "test-segment-key",
        "DATABASES": {"default": {"PASSWORD": "test-db-password", "NAME": "metrics_service"}},
        "TASK_TIMEOUT": 3600,
    }

    with patch("metrics_service.settings.DYNACONF", dynaconf):
        result = collectors.collect_settings()

    serialized = json.dumps(result)
    assert "test-secret-key-value" not in serialized
    assert "test-segment-key" not in serialized
    assert "test-db-password" not in serialized
    assert result["settings"]["TASK_TIMEOUT"] == 3600
    assert result["_redaction"]["redacted_key_count"] == 3
