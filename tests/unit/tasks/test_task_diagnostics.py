"""Unit tests for task diagnostics queries and text rendering."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.tasks.diagnostics import (
    get_diagnostics,
    get_dispatcherd_state,
    get_failure_counts,
    get_last_success_by_function,
    get_queue_depth,
    get_stuck_tasks,
    render_diagnostics_text,
)
from apps.tasks.models import Task, TaskExecution

TIMEOUT = 3600


def _task(user, name="Task", function_name="hello_world", status="pending", started_at=None, **kwargs):
    return Task.objects.create(
        name=name,
        function_name=function_name,
        status=status,
        started_at=started_at,
        created_by=user,
        **kwargs,
    )


def _execution(task, status, completed_at=None, error_message="", worker_id=None):
    execution = TaskExecution.objects.create(
        task=task, status=status, completed_at=completed_at, error_message=error_message, worker_id=worker_id
    )
    return execution


@pytest.mark.unit
@pytest.mark.django_db
class TestGetStuckTasks:
    def test_running_task_beyond_timeout_is_returned_with_duration(self, user):
        now = timezone.now()
        task = _task(
            user,
            name="Stuck Task",
            status="running",
            started_at=now - timedelta(seconds=TIMEOUT + 60),
        )

        results = get_stuck_tasks(stuck_timeout=TIMEOUT, now=now)

        assert len(results) == 1
        row = results[0]
        assert row["task_id"] == task.id
        assert row["name"] == "Stuck Task"
        assert row["duration_seconds"] >= TIMEOUT + 60

    def test_running_task_inside_timeout_is_not_returned(self, user):
        now = timezone.now()
        _task(user, status="running", started_at=now - timedelta(seconds=60))

        assert get_stuck_tasks(stuck_timeout=TIMEOUT, now=now) == []

    @pytest.mark.parametrize("status", ["pending", "completed", "failed", "cancelled"])
    def test_non_running_tasks_are_never_returned(self, user, status):
        now = timezone.now()
        _task(user, status=status, started_at=now - timedelta(seconds=TIMEOUT + 60))

        assert get_stuck_tasks(stuck_timeout=TIMEOUT, now=now) == []

    def test_running_task_without_started_at_is_excluded(self, user):
        now = timezone.now()
        _task(user, status="running", started_at=None)

        assert get_stuck_tasks(stuck_timeout=TIMEOUT, now=now) == []

    def test_worker_details_and_reported_by(self, user):
        now = timezone.now()
        task = _task(user, status="running", started_at=now - timedelta(seconds=TIMEOUT + 5))
        execution = _execution(task, "running", worker_id="dispatcher-1234")

        live_state = {
            "live_available": True,
            "running": {"worker-2": {"kwargs": {"task_id": task.id}}},
        }
        results = get_stuck_tasks(stuck_timeout=TIMEOUT, now=now, live_state=live_state)

        assert results[0]["worker_id"] == "dispatcher-1234"
        assert results[0]["execution_id"] == execution.id
        assert results[0]["reported_by"] == ["worker-2"]

    def test_unreported_when_no_live_worker(self, user):
        now = timezone.now()
        _task(user, status="running", started_at=now - timedelta(seconds=TIMEOUT + 5))

        results = get_stuck_tasks(stuck_timeout=TIMEOUT, now=now, live_state=None)

        assert results[0]["reported_by"] == []


@pytest.mark.unit
@pytest.mark.django_db
class TestGetLastSuccessByFunction:
    def test_max_completed_at_per_function(self, user):
        now = timezone.now()
        task = _task(user, function_name="hello_world", status="completed")
        _execution(task, "completed", completed_at=now - timedelta(hours=5))
        _execution(task, "completed", completed_at=now - timedelta(hours=1))

        results = get_last_success_by_function(now=now)
        by_function = {row["function_name"]: row for row in results}

        assert by_function["hello_world"]["last_success_at"] is not None
        assert by_function["hello_world"]["age_seconds"] == pytest.approx(3600, abs=5)
        assert by_function["hello_world"]["task_name"] == "Task"

    def test_never_succeeded_function_included_as_null(self, user):
        results = get_last_success_by_function(now=timezone.now())
        by_function = {row["function_name"]: row for row in results}

        # A registered function with no executions must still be reported.
        assert "collect_hourly_metrics" in by_function
        assert by_function["collect_hourly_metrics"]["last_success_at"] is None
        # Never-succeeded rows sort first.
        assert results[0]["last_success_at"] is None

    def test_failed_executions_do_not_count_as_success(self, user):
        now = timezone.now()
        task = _task(user, function_name="hello_world", status="failed")
        _execution(task, "failed", completed_at=now - timedelta(minutes=5))

        by_function = {row["function_name"]: row for row in get_last_success_by_function(now=now)}

        assert by_function["hello_world"]["last_success_at"] is None


@pytest.mark.unit
@pytest.mark.django_db
class TestGetFailureCounts:
    def test_window_excludes_older_failures(self, user):
        now = timezone.now()
        task = _task(user, function_name="hello_world", status="failed")
        _execution(task, "failed", completed_at=now - timedelta(hours=25), error_message="old")

        assert get_failure_counts(hours=24, now=now) == []

        results = get_failure_counts(hours=48, now=now)
        assert results[0]["failure_count"] == 1

    def test_grouped_with_last_failure_and_error(self, user):
        now = timezone.now()
        task = _task(user, function_name="hello_world", status="failed")
        _execution(task, "failed", completed_at=now - timedelta(hours=3), error_message="first")
        _execution(task, "failed", completed_at=now - timedelta(hours=1), error_message="latest")

        results = get_failure_counts(hours=24, now=now)

        assert len(results) == 1
        row = results[0]
        assert row["function_name"] == "hello_world"
        assert row["failure_count"] == 2
        assert row["last_failure_at"] is not None
        assert row["last_error"] == "latest"

    def test_same_function_across_task_names_aggregated(self, user):
        now = timezone.now()
        task_one = _task(user, name="One", function_name="hello_world", status="failed")
        task_two = _task(user, name="Two", function_name="hello_world", status="failed")
        _execution(task_one, "failed", completed_at=now - timedelta(hours=2))
        _execution(task_two, "failed", completed_at=now - timedelta(hours=1))

        results = get_failure_counts(hours=24, now=now)

        assert len(results) == 1
        assert results[0]["failure_count"] == 2

    def test_legacy_failed_task_without_execution_is_counted(self, user):
        now = timezone.now()
        Task.objects.create(
            name="Legacy",
            function_name="hello_world",
            status="failed",
            completed_at=now - timedelta(hours=1),
            error_message="legacy failure",
            created_by=user,
        )

        results = get_failure_counts(hours=24, now=now)

        assert results[0]["failure_count"] == 1
        assert results[0]["legacy_task_failures"] == 1
        assert results[0]["last_error"] == "legacy failure"


@pytest.mark.unit
@pytest.mark.django_db
class TestQueueDepth:
    def test_pending_tasks_counted_by_queue(self, user):
        _task(user, function_name="collect_hourly_metrics", status="pending")
        _task(user, function_name="collect_hourly_metrics", status="pending")
        _task(user, function_name="hello_world", status="pending")

        result = get_queue_depth(live_state=None)
        by_queue = {row["queue"]: row for row in result["queues"]}

        assert by_queue["metrics"]["pending_in_db"] == 2
        assert by_queue["maintenance"]["pending_in_db"] == 1
        assert result["live_available"] is False

    def test_live_queue_depth_counted(self, user):
        task = _task(user, function_name="collect_hourly_metrics", status="pending")
        live_state = {
            "live_available": True,
            "running": {f"queued-{index}": {"kwargs": {"task_id": task.id}} for index in range(2)},
            "workers": [],
            "producers": [],
        }

        result = get_queue_depth(live_state=live_state)
        by_queue = {row["queue"]: row for row in result["queues"]}

        assert by_queue["metrics"]["queued_live"] == 2
        assert result["live_available"] is True

    def test_dispatcherd_failure_degrades_gracefully(self):
        with patch(
            "apps.tasks.dispatcherd_config.ensure_dispatcherd_configured",
            side_effect=ImportError("dispatcherd not installed"),
        ):
            state = get_dispatcherd_state()

        assert state["live_available"] is False
        assert "ImportError" in state["error"]

    @pytest.mark.django_db
    def test_db_depth_returned_when_live_unavailable(self, user):
        _task(user, function_name="hello_world", status="pending")
        live_state = {"live_available": False, "running": {}, "workers": [], "producers": [], "error": "boom"}

        result = get_queue_depth(live_state=live_state)
        by_queue = {row["queue"]: row for row in result["queues"]}

        assert by_queue["maintenance"]["pending_in_db"] == 1


@pytest.mark.unit
@pytest.mark.django_db
class TestGetDiagnostics:
    def test_schema_and_top_level_keys(self, user):
        now = timezone.now()
        _task(user, status="running", started_at=now - timedelta(seconds=TIMEOUT + 60))

        with patch("apps.tasks.diagnostics.get_dispatcherd_state") as mock_state:
            mock_state.return_value = {
                "live_available": False,
                "running": {},
                "workers": [],
                "producers": [],
                "error": "test",
            }
            data = get_diagnostics()

        assert data["schema_version"] == 1
        assert data["task_timeout_seconds"] == TIMEOUT
        assert data["window_hours"] == 24
        assert set(data) >= {
            "generated_at",
            "stuck_tasks",
            "last_success",
            "failures_last_24h",
            "queue_depth",
        }
        assert len(data["stuck_tasks"]) == 1


@pytest.mark.unit
class TestRenderDiagnosticsText:
    def _data(self):
        return {
            "schema_version": 1,
            "generated_at": "2026-11-03T12:00:00+00:00",
            "task_timeout_seconds": 3600,
            "window_hours": 24,
            "stuck_tasks": [],
            "last_success": [
                {
                    "function_name": "hello_world",
                    "last_success_at": None,
                    "age_seconds": None,
                    "task_name": None,
                }
            ],
            "failures_last_24h": [],
            "queue_depth": {
                "live_available": False,
                "error": "nope",
                "queues": [
                    {"queue": "maintenance", "pending_in_db": 0, "queued_live": 0, "blocked_live": 0, "delayed_live": 0}
                ],
                "dispatcherd_workers": [],
                "dispatcherd_producers": [],
            },
        }

    def test_section_headers_and_empty_state(self):
        text = render_diagnostics_text(self._data())

        assert "Metrics service task diagnostics" in text
        assert "Stuck tasks (0)" in text
        assert "No stuck tasks." in text
        assert "Last successful run by task type" in text
        assert "Failures in the last 24h" in text
        assert "No failures in the window." in text
        assert "Queue depth" in text
        assert "Live dispatcherd state unavailable: nope" in text
        assert "Use --format json for scripting." in text

    def test_error_text_truncated_and_collapsed(self):
        data = self._data()
        data["failures_last_24h"] = [
            {
                "function_name": "hello_world",
                "failure_count": 1,
                "last_failure_at": "2026-11-03T11:00:00+00:00",
                "last_error": "line one\nline two " + "x" * 500,
            }
        ]

        text = render_diagnostics_text(data)

        assert "line one line two" in text
        assert "\nline two" not in text
        assert "x" * 500 not in text
