"""Unit tests for support-bundle collectors."""

import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.analytics.models import AnalyticsPayload
from apps.core.support_bundle import bundle, collectors
from apps.core.support_bundle.redaction import REDACTED
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
        self.calls = []

    def control_with_reply(self, command, expected_replies=1, timeout=1.0, data=None):
        self.calls.append(command)
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
def test_collect_queues_reports_unavailable_when_nothing_answers():
    """A dead broker returns [] after the timeout instead of raising."""
    with (
        patch.object(collectors, "ensure_dispatcherd_configured"),
        patch.object(collectors, "get_control_from_settings", return_value=FakeControl({})),
    ):
        result = collectors.collect_queues()

    assert result["live_available"] is False
    assert result["dispatcherd"]["available"] is False
    assert "no replies from dispatcherd" in result["dispatcherd"]["error"]
    assert result["dispatcherd"]["partial"] is False
    assert result["dispatcherd"]["node_count"] == 0
    assert result["dispatcherd"]["reply_counts"] == {"running": 0, "workers": 0, "producers": 0}


@pytest.mark.django_db
def test_collect_tasks_reports_unavailable_when_nothing_answers():
    Task.objects.create(name="pending", function_name="hello_world", status="pending")

    with (
        patch.object(collectors, "ensure_dispatcherd_configured"),
        patch.object(collectors, "get_control_from_settings", return_value=FakeControl({})),
    ):
        result = collectors.collect_tasks()

    assert result["dispatcherd"]["available"] is False
    assert "no replies from dispatcherd" in result["dispatcherd"]["error"]
    assert result["dispatcherd"]["running"] == {}
    assert result["dispatcherd"]["workers"] == {}
    assert result["tasks"][0]["source"] == "db"


@pytest.mark.django_db
def test_collect_tasks_aggregates_replies_from_every_node():
    Task.objects.create(name="pending", function_name="hello_world", status="pending")

    replies = {
        "running": [
            {"worker-0": {"task": "hello_world", "uuid": "uuid-0"}, "node_id": "node-1"},
            {"worker-1": {"task": "collect_hourly_metrics", "uuid": "uuid-1"}, "node_id": "node-2"},
        ],
        "workers": [
            {"worker-0": {"status": "idle"}, "node_id": "node-1"},
            {"worker-1": {"status": "running"}, "node_id": "node-2"},
        ],
    }
    with (
        patch.object(collectors, "ensure_dispatcherd_configured"),
        patch.object(collectors, "get_control_from_settings", return_value=FakeControl(replies)),
    ):
        result = collectors.collect_tasks()

    dispatcherd = result["dispatcherd"]
    assert dispatcherd["available"] is True
    assert dispatcherd["partial"] is False
    assert dispatcherd["nodes"] == ["node-1", "node-2"]
    assert dispatcherd["node_count"] == 2
    assert set(dispatcherd["running"]) == {"worker-0", "worker-1"}
    assert set(dispatcherd["workers"]) == {"worker-0", "worker-1"}
    assert "node_id" not in dispatcherd["running"]


@pytest.mark.django_db
def test_collect_tasks_marks_partial_when_a_control_command_is_silent():
    replies = {"running": [{"worker-0": {"task": "hello_world"}, "node_id": "node-1"}], "workers": []}
    with (
        patch.object(collectors, "ensure_dispatcherd_configured"),
        patch.object(collectors, "get_control_from_settings", return_value=FakeControl(replies)),
    ):
        result = collectors.collect_tasks()

    assert result["dispatcherd"]["available"] is True
    assert result["dispatcherd"]["partial"] is True
    assert result["dispatcherd"]["reply_counts"] == {"running": 1, "workers": 0}


def test_control_probe_respects_the_total_time_budget():
    control = FakeControl({"running": [{"worker-0": {"task": "hello_world"}}]})

    with patch.object(collectors, "get_control_from_settings", return_value=control):
        replies = collectors._probe_control(("running", "workers", "producers"), total_timeout=-1)

    assert replies == {"running": [], "workers": [], "producers": []}
    assert control.calls == []


@pytest.mark.django_db
def test_control_request_echo_is_not_mistaken_for_a_live_node():
    """A broker echo of ``{"control": ..., "reply_to": ...}`` is not a reply."""
    echoes = {
        "running": [{"control": "running", "reply_to": "reply_to_abc"}],
        "workers": [{"control": "workers", "reply_to": "reply_to_def"}],
    }
    with (
        patch.object(collectors, "ensure_dispatcherd_configured"),
        patch.object(collectors, "get_control_from_settings", return_value=FakeControl(echoes)),
    ):
        result = collectors.collect_tasks()

    assert result["dispatcherd"]["available"] is False
    assert "no replies from dispatcherd" in result["dispatcherd"]["error"]
    assert result["dispatcherd"]["reply_counts"] == {"running": 0, "workers": 0}


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


def test_build_bundle_redacts_every_section_before_serialisation():
    """Free-text errors and raw dispatcherd replies must not reach the tarball."""
    leaky_tasks = {
        "task_timeout_seconds": 3600,
        "dispatcherd": {
            "available": True,
            "running": {"queued-0": {"task": "send_report", "args": ["--password=hunter2", "keep-me"]}},
            "workers": {"worker-0": {"status": "idle"}},
        },
        "tasks": [],
    }
    leaky_ingestion = {
        "collectors": [
            {"collector_type": "unified_jobs", "last_error_message": "POST https://segment/api?token=abc123 (401)"},
            {"collector_type": "metrics", "last_error_message": "curl --password=hunter2 --user=admin"},
            {"collector_type": "other", "last_error_message": "SEGMENT_WRITE_KEY=abc123"},
        ],
        "segment": [{"error_message": "redis://:redispw@cache:6379/0 refused"}],
    }
    leaky_queues = {"dispatcherd": {"producers": {"p-0": {"status": "Bearer abc.def.ghi"}}}}

    with (
        patch.dict(
            bundle.COLLECTORS,
            {
                "tasks.json": lambda: leaky_tasks,
                "ingestion.json": lambda: leaky_ingestion,
                "queues.json": lambda: leaky_queues,
                "schema.json": lambda: {"connected": True},
                "settings.json": lambda: {"settings": {"SECRET_KEY": "s3cr3t"}},
            },
        ),
        patch.object(bundle, "collect_meta", return_value={"generated_at": "now"}),
    ):
        sections = bundle.build_bundle()

    serialized = json.dumps(sections)
    for secret in ("abc123", "hunter2", "redispw", "s3cr3t", "abc.def.ghi"):
        assert secret not in serialized
    # Structure survives redaction; only the secrets are replaced.
    assert set(sections) == set(bundle.COLLECTORS)
    assert sections["tasks.json"]["dispatcherd"]["running"]["queued-0"]["task"] == "send_report"
    assert sections["tasks.json"]["dispatcherd"]["running"]["queued-0"]["args"][1] == "keep-me"
    assert "hunter2" not in str(sections["tasks.json"]["dispatcherd"]["running"]["queued-0"]["args"])
    assert sections["ingestion.json"]["collectors"][0]["collector_type"] == "unified_jobs"
    assert sections["tasks.json"]["meta"] == {"generated_at": "now"}


def _walk(node, path=""):
    """Yield ``(dotted_path, key, value)`` for every node in *node*."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield child, key, value
            yield from _walk(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = f"{path}[{index}]"
            yield child, index, value
            yield from _walk(value, child)


def _full_bundle_collectors(dynaconf):
    """Five collectors shaped like the real bundle, including the real settings pass."""

    def settings_section():
        with patch("metrics_service.settings.DYNACONF", dynaconf):
            return collectors.collect_settings()

    return {
        "tasks.json": lambda: {
            "task_timeout_seconds": 3600,
            "dispatcherd": {
                "available": True,
                "partial": False,
                "nodes": ["node-a"],
                "node_count": 1,
                "reply_counts": {"running": 1, "workers": 1},
                "running": {"queued-0": {"task": "send_report", "args": ["--api-key=abc123"]}},
                "workers": {"worker-0": {"status": "idle"}},
            },
            "tasks": [],
            "stuck_task_ids": [],
            "task_count": 0,
        },
        "ingestion.json": lambda: {
            "dimension": "collector",
            "collectors": [
                {
                    "collector_type": "unified_jobs",
                    "consecutive_failures": 0,
                    "last_error_message": "failed to POST https://segment/api?token=abc123 (401)",
                }
            ],
            "daily_summaries": [
                {
                    "summary_date": "2026-11-05",
                    "hourly_collections_count": 24,
                    "missing_hours_count": 0,
                }
            ],
            "segment": [{"retry_count": 2, "error_message": "redis://:redispw@cache:6379/0 refused"}],
            "analytics_payloads": [{"collector": "main", "cluster_id": "cluster-123", "source": "scheduler"}],
        },
        "queues.json": lambda: {
            "queues": [{"name": "dashboard", "db_pending": 0}],
            "db_pending_total": 0,
            "dispatcherd": {
                "available": True,
                "partial": True,
                "nodes": ["node-a"],
                "node_count": 1,
                "reply_counts": {"running": 1, "workers": 0, "producers": 0},
                "workers": {"worker-0": {"status": "idle"}},
                "producers": {"p-0": {"status": "ok"}},
            },
            "live_available": True,
        },
        "schema.json": lambda: {
            "connected": True,
            "applied_migrations_count": 42,
            "unapplied_migrations_count": 0,
        },
        "settings.json": settings_section,
    }


def test_full_bundle_keeps_metadata_numbers_and_still_redacts_secrets():
    """The whole bundle, as shipped, keeps counts and strips credentials.

    The collectors tests used to assert on ``collect_settings()`` in isolation,
    which hid a global-pass bug: ``_redaction.redacted_key_count`` was replaced
    by the redaction marker because its *name* contains ``KEY``. This test builds
    all five sections through :func:`bundle.build_bundle` and inspects the
    serialized result.
    """
    dynaconf = Mock()
    dynaconf.as_dict.return_value = {
        "SECRET_KEY": "test-secret-key-value",
        "SEGMENT_WRITE_KEY": "test-segment-key",
        "DATABASES": {"default": {"PASSWORD": "test-db-password", "NAME": "metrics_service"}},
        "TASK_TIMEOUT": 3600,
        "TOKEN_BUDGET": 100,
        "PASSWORD_POLICY": "min-length-12",
    }

    with (
        patch.dict(bundle.COLLECTORS, _full_bundle_collectors(dynaconf)),
        patch.object(bundle, "collect_meta", return_value={"generated_at": "now"}),
    ):
        sections = bundle.build_bundle()

    serialized = json.dumps(sections)

    # 1. The shipped summary field is a count, not the redaction marker.
    redaction = sections["settings.json"]["_redaction"]
    assert isinstance(redaction["redacted_key_count"], int)
    assert redaction["redacted_key_count"] == 3
    assert redaction["redacted_paths"] == [
        "DATABASES.default.PASSWORD",
        "SECRET_KEY",
        "SEGMENT_WRITE_KEY",
    ]

    # 2. Every counter/measurement survives as a number.
    safe_suffixes = ("_count", "_counts", "_budget", "_ms", "_seconds", "_bytes", "_policy")
    for path, key, value in _walk(sections):
        if not isinstance(key, str):
            continue
        if key.lower().endswith(("_count", "_ms")):
            assert isinstance(value, (int, float)), f"{path} should be numeric, got {value!r}"
        if key.lower().endswith(safe_suffixes):
            assert value != REDACTED, f"{path} is metadata and must not be redacted"

    assert sections["tasks.json"]["task_count"] == 0
    assert sections["tasks.json"]["task_timeout_seconds"] == 3600
    assert sections["tasks.json"]["dispatcherd"]["node_count"] == 1
    assert sections["ingestion.json"]["daily_summaries"][0]["hourly_collections_count"] == 24
    assert sections["ingestion.json"]["daily_summaries"][0]["missing_hours_count"] == 0
    assert sections["ingestion.json"]["segment"][0]["retry_count"] == 2
    assert sections["queues.json"]["db_pending_total"] == 0
    assert sections["schema.json"]["applied_migrations_count"] == 42
    assert sections["schema.json"]["unapplied_migrations_count"] == 0
    assert sections["settings.json"]["settings"]["TASK_TIMEOUT"] == 3600
    assert sections["settings.json"]["settings"]["TOKEN_BUDGET"] == 100
    assert sections["settings.json"]["settings"]["PASSWORD_POLICY"] == "min-length-12"

    # 3. Genuine secrets are still gone (values and key-based).
    for secret in (
        "test-secret-key-value",
        "test-segment-key",
        "test-db-password",
        "abc123",
        "redispw",
    ):
        assert secret not in serialized
    assert sections["settings.json"]["settings"]["SECRET_KEY"] == REDACTED
    assert sections["settings.json"]["settings"]["SEGMENT_WRITE_KEY"] == REDACTED
    assert sections["settings.json"]["settings"]["DATABASES"]["default"]["PASSWORD"] == REDACTED

    # 4. Other shape keys that contain a marker as a substring survive.
    assert sections["ingestion.json"]["analytics_payloads"][0]["cluster_id"] == "cluster-123"
    assert sections["tasks.json"]["dispatcherd"]["reply_counts"] == {"running": 1, "workers": 1}
    assert sections["tasks.json"]["dispatcherd"]["partial"] is False
    assert sections["queues.json"]["dispatcherd"]["partial"] is True
    assert sections["queues.json"]["dispatcherd"]["available"] is True
    assert sections["queues.json"]["live_available"] is True

    # 5. The bundle is still valid JSON end to end.
    assert json.loads(serialized) == sections
