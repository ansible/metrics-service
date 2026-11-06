"""Unit tests for task diagnostics queries and text rendering."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.tasks.diagnostics import (
    get_diagnostics,
    get_dispatcherd_state,
    get_failure_counts,
    get_known_queues,
    get_last_success_by_function,
    get_queue_depth,
    get_stuck_tasks,
    render_diagnostics_text,
)
from apps.tasks.models import Task, TaskExecution

TIMEOUT = 3600


class _FakeControl:
    """Minimal stand-in for dispatcherd's ``Control`` with canned replies."""

    def __init__(self, replies=None, errors=None):
        self.replies = replies or {}
        self.errors = errors or {}
        self.calls = []

    def control_with_reply(self, command, timeout=None):
        self.calls.append((command, timeout))
        if command in self.errors:
            raise self.errors[command]
        return list(self.replies.get(command, []))


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

    def test_legacy_task_failures_key_present_on_execution_rows(self, user):
        """The row schema is stable: every row carries legacy_task_failures."""
        now = timezone.now()
        task = _task(user, function_name="hello_world", status="failed")
        _execution(task, "failed", completed_at=now - timedelta(hours=1))

        results = get_failure_counts(hours=24, now=now)

        assert results[0]["legacy_task_failures"] == 0


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


def _live_state_with(control):
    """Run get_dispatcherd_state against a fake dispatcherd control."""
    with (
        patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"),
        patch("dispatcherd.factories.get_control_from_settings", return_value=control),
    ):
        return get_dispatcherd_state(timeout=0.01)


#: Reply captured on 2026-11-06 from a **real** single-node dispatcherd 2026.1.27
#: daemon started as
#: ``METRICS_SERVICE_DATABASES__default__NAME=test_metrics_service_a531b \
#:      python manage.py run_dispatcherd --workers 2``
#: on the pg_notify broker, via
#: ``Control("pg_notify", <broker config>, queue="dashboard").control_with_reply(cmd)``.
#: This deployment's ``Control.queuename`` is ``None``, so the stock
#: ``get_control_from_settings()`` publishes the request onto its own reply queue
#: and only ever receives the echo below; an explicit ``queue`` is what makes the
#: daemon answer at all. Note the string ``node_id`` on every reply, the
#: ``ready`` worker status, and that ``running`` carries metadata only because
#: the node was idle.
REAL_HEALTHY_REPLIES = {
    "running": [{"node_id": "b605ecf3-7ef0-4aa8-a70b-d94cd6952ae8"}],
    "workers": [
        {
            "worker-0": {
                "worker_id": 0,
                "pid": 65706,
                "status": "ready",
                "finished_count": 0,
                "current_task": None,
                "current_task_uuid": None,
                "active_cancel": False,
                "age": 29.597034708000137,
            },
            "node_id": "b605ecf3-7ef0-4aa8-a70b-d94cd6952ae8",
        }
    ],
    "producers": [
        {
            "pg_notify-producer": {
                "produced_count": 3,
                "uptime_seconds": 29.61463337499299,
                "recycle_count": 0,
                "broker_self_check": {
                    "enabled": True,
                    "success_count": 0,
                    "average_time_seconds": None,
                    "max_time_seconds": None,
                },
            },
            "node_id": "b605ecf3-7ef0-4aa8-a70b-d94cd6952ae8",
        }
    ],
}

#: Reply captured on 2026-11-06 with **no dispatcherd daemon running**
#: (``pgrep -f run_dispatcherd`` empty) against the real pg_notify broker, using
#: the production path ``get_control_from_settings().control_with_reply(cmd)``.
#: The broker echoes the control request back on the reply channel, so this is
#: the shape a "no daemon" deployment actually produces -- nothing here may be
#: read as a live worker or producer.
REAL_ECHO_ONLY_REPLIES = {
    "running": [{"control": "running", "reply_to": "reply_to_e28c35f9_fdfd_4e49_869e_4e67035c134d"}],
    "workers": [{"control": "workers", "reply_to": "reply_to_48ed564a_7b62_49b6_ba8c_20fa8974f08d"}],
    "producers": [{"control": "producers", "reply_to": "reply_to_86b7ead0_4af9_4087_9089_5a604c5cb88d"}],
}


@pytest.mark.unit
class TestGetDispatcherdState:
    def test_no_daemon_replies_marks_live_unavailable(self):
        """No daemon means no replies after the timeout, not a healthy idle system."""
        control = _FakeControl()

        state = _live_state_with(control)

        assert state["live_available"] is False
        assert state["error"] == "no replies from dispatcherd (control timeout)"
        assert state["workers"] == []
        assert state["producers"] == []

    def test_real_echo_only_replies_mark_live_unavailable(self):
        """The pg_notify broker echoes the request back when no daemon consumes it."""
        control = _FakeControl(replies={command: list(r) for command, r in REAL_ECHO_ONLY_REPLIES.items()})

        state = _live_state_with(control)

        assert state["live_available"] is False
        assert state["error"] == "no replies from dispatcherd (control timeout)"
        assert state["running"] == {}
        assert state["workers"] == []
        assert state["producers"] == []
        assert state["warnings"] == []

    def test_real_healthy_reply_is_available_without_spurious_warnings(self):
        """A real single-node reply must not be mistaken for a broken dispatcher."""
        control = _FakeControl(replies={command: list(r) for command, r in REAL_HEALTHY_REPLIES.items()})

        state = _live_state_with(control)

        assert state["live_available"] is True
        assert state["error"] is None
        assert state["warnings"] == []
        assert state["query_errors"] == {}
        # node_id is reply metadata: it is neither a worker nor a stomped running key.
        assert state["running"] == {}
        assert state["workers"] == [REAL_HEALTHY_REPLIES["workers"][0]["worker-0"]]
        assert [producer["producer"] for producer in state["producers"]] == ["pg_notify-producer"]
        assert state["producers"][0]["produced_count"] == 3

    def test_echo_alongside_a_real_reply_is_ignored(self):
        """A node that answers is live even if the broker also echoes the request."""
        control = _FakeControl(
            replies={
                "running": list(REAL_HEALTHY_REPLIES["running"]),
                "workers": [REAL_ECHO_ONLY_REPLIES["workers"][0], *REAL_HEALTHY_REPLIES["workers"]],
                "producers": [REAL_ECHO_ONLY_REPLIES["producers"][0], *REAL_HEALTHY_REPLIES["producers"]],
            }
        )

        state = _live_state_with(control)

        assert state["live_available"] is True
        assert state["warnings"] == []
        assert len(state["workers"]) == 1
        assert [producer["producer"] for producer in state["producers"]] == ["pg_notify-producer"]

    def test_reply_level_error_is_surfaced_not_counted_as_worker(self):
        """An unknown control method answers with ``{"error": ...}`` plus node_id."""
        control = _FakeControl(replies={"workers": [{"error": "No control method workers", "node_id": "node-1"}]})

        state = _live_state_with(control)

        assert state["live_available"] is True
        assert state["workers"] == []
        assert state["warnings"] == ["workers query failed: dispatcherd error: No control method workers"]

    def test_reply_from_daemon_marks_live_available(self):
        control = _FakeControl(replies={"running": [{"worker-0": {"kwargs": {"task_id": 7}}}]})

        state = _live_state_with(control)

        assert state["live_available"] is True
        assert state["error"] is None
        assert state["running"] == {"worker-0": {"kwargs": {"task_id": 7}}}

    def test_non_dict_worker_values_are_filtered_at_ingestion(self):
        """dispatcherd's own JSON-parse-error reply yields string values."""
        control = _FakeControl(
            replies={
                "workers": [
                    {"error": "JSON parse error", "original": "{bad"},
                    {"0": {"worker_id": 0, "status": "idle"}},
                ]
            }
        )

        state = _live_state_with(control)

        assert state["live_available"] is True
        assert state["workers"] == [{"worker_id": 0, "status": "idle"}]
        assert any("malformed" in warning for warning in state["warnings"])

    def test_one_failing_query_keeps_other_replies_and_records_error(self):
        control = _FakeControl(
            replies={"running": [{"worker-1": {"kwargs": {"task_id": 3}}}]},
            errors={"workers": RuntimeError("broker gone")},
        )

        state = _live_state_with(control)

        assert state["live_available"] is True
        assert state["running"] == {"worker-1": {"kwargs": {"task_id": 3}}}
        assert "RuntimeError: broker gone" in state["query_errors"]["workers"]
        assert any("workers query failed" in warning for warning in state["warnings"])


@pytest.mark.unit
class TestKnownQueues:
    def test_queues_read_from_dispatcherd_config(self):
        assert set(get_known_queues()) == {"dashboard", "maintenance", "metrics"}

    def test_queues_read_from_configured_yaml(self, tmp_path, monkeypatch):
        config = tmp_path / "dispatcherd.yaml"
        config.write_text(
            "version: 2\nbrokers:\n  pg_notify:\n    channels:\n      - alpha\n      - beta\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("DISPATCHERD_CONFIG_FILE", str(config))

        assert get_known_queues() == ("alpha", "beta")

    def test_fallback_when_config_file_is_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DISPATCHERD_CONFIG_FILE", str(tmp_path / "absent.yaml"))

        assert get_known_queues() == ("dashboard", "maintenance", "metrics")


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

        assert data["schema_version"] == 2
        assert data["task_timeout_seconds"] == TIMEOUT
        assert data["window_hours"] == 24
        assert set(data) >= {
            "generated_at",
            "stuck_tasks",
            "last_success",
            "failures_in_window",
            "queue_depth",
        }
        assert "failures_last_24h" not in data
        assert len(data["stuck_tasks"]) == 1


@pytest.mark.unit
class TestRenderDiagnosticsText:
    def _data(self):
        return {
            "schema_version": 2,
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
            "failures_in_window": [],
            "queue_depth": {
                "live_available": False,
                "error": "nope",
                "warnings": [],
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
        data["failures_in_window"] = [
            {
                "function_name": "hello_world",
                "failure_count": 1,
                "legacy_task_failures": 0,
                "last_failure_at": "2026-11-03T11:00:00+00:00",
                "last_error": "line one\nline two " + "x" * 500,
            }
        ]

        text = render_diagnostics_text(data)

        assert "line one line two" in text
        assert "\nline two" not in text
        assert "x" * 500 not in text

    def test_dict_workers_rendered(self):
        data = self._data()
        data["queue_depth"] = {
            "live_available": True,
            "error": None,
            "warnings": [],
            "queues": [],
            "dispatcherd_workers": [{"worker_id": 0, "status": "idle", "current_task": None}],
            "dispatcherd_producers": [{"producer": "scheduler", "produced_count": 4}],
        }

        text = render_diagnostics_text(data)

        assert "Workers: 1 | Producers: 1" in text
        assert "worker-0: idle | current task: idle" in text
        assert "scheduler: produced 4" in text

    def test_non_dict_worker_and_producer_entries_do_not_crash(self):
        """Regression: dispatcherd error replies made the text renderer raise AttributeError."""
        data = self._data()
        data["queue_depth"] = {
            "live_available": True,
            "error": None,
            "warnings": ["ignored 1 malformed dispatcherd worker entries"],
            "queues": [],
            "dispatcherd_workers": ["idle", {"worker_id": 0, "status": "idle", "current_task": None}],
            "dispatcherd_producers": ["bogus"],
        }

        text = render_diagnostics_text(data)

        assert "worker-0: idle" in text
        assert "Warning: ignored 1 malformed dispatcherd worker entries" in text
        assert "Warning: unexpected worker entry 'idle'" in text
        assert "Warning: unexpected producer entry 'bogus'" in text

    def test_limit_matches_row_count(self):
        data = self._data()
        data["stuck_tasks"] = [
            {
                "task_id": index,
                "name": f"Stuck {index}",
                "function_name": "hello_world",
                "started_at": "2026-11-03T10:00:00+00:00",
                "duration_seconds": 7200,
                "attempts": 1,
                "worker_id": None,
                "execution_id": None,
                "reported_by": [],
            }
            for index in range(3)
        ]

        text = render_diagnostics_text(data, limit=2)

        assert "Stuck tasks (3)" in text
        assert text.count("Function: hello_world") == 2
