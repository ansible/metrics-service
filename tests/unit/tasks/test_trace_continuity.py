"""
Tier 1 trace-continuity regression tests (AAP-79590).

Verify end-to-end, fully in-process, that a ``request_id`` originating from an
API call appears on the log records emitted by the worker that executed the
resulting task. Every piece of *our* code on the path is exercised:

    middleware → Task.request_id → submit_task_to_dispatcher payload →
    execute_db_task context → log records

with only the dispatcherd broker mocked at the ``dispatcherd.publish.submit_task``
boundary. The cross-process variants live in
``tests/integration/test_trace_continuity_process.py`` (opt-in) and in
``docs/trace-propagation.md`` (manual procedure).
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.core.request_context import request_context
from apps.tasks.models import DailyMetricsSummary, Task
from apps.tasks.tasks import submit_task_to_dispatcher
from apps.tasks.tasks_system import execute_db_task
from tests.unit.tasks.conftest import TRACE_REQUEST_ID

User = get_user_model()


def _schedule_immediate(api_client, user, *, request_id=None):
    """POST a hello_world task, optionally with an inbound X-Request-ID."""
    api_client.force_authenticate(user=user)
    headers = {"HTTP_X_REQUEST_ID": request_id} if request_id is not None else {}
    return api_client.post(
        reverse("tasks:v1:task-schedule-immediate"),
        {"name": "trace-check", "function_name": "hello_world", "task_data": {}},
        format="json",
        **headers,
    )


def _submit_and_capture_payload(task):
    """Submit through our code with the dispatcherd broker mocked; return the payload."""
    with (
        patch("dispatcherd.publish.submit_task") as submit,
        patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"),
        patch("apps.tasks.tasks.get_queue_for_function", return_value="metrics"),
    ):
        submit_task_to_dispatcher(task)
    submit.assert_called_once()
    return submit.call_args.kwargs["kwargs"]


def _worker_records(trace_records):
    return [r for r in trace_records if r.name.startswith("apps.tasks")]


@pytest.mark.unit
@pytest.mark.django_db
class TestTraceContinuity:
    """A request ID survives the API → Task row → payload → worker log path."""

    def test_request_id_reaches_worker_logs(self, api_client, user, trace_records):
        response = _schedule_immediate(api_client, user, request_id=TRACE_REQUEST_ID)
        assert response.status_code == 200
        assert response["X-Request-ID"] == TRACE_REQUEST_ID

        task = Task.objects.get(id=response.data["task_id"])
        assert task.request_id == TRACE_REQUEST_ID

        payload = _submit_and_capture_payload(task)
        assert payload == {"task_id": task.id, "request_id": TRACE_REQUEST_ID}

        # Worker execution with the exact kwargs dispatcherd would deliver.
        trace_records.clear()
        result = execute_db_task(**payload)
        assert result["status"] == "success"

        worker_records = _worker_records(trace_records)
        assert worker_records, "worker emitted no log records"
        assert {r.request_id for r in worker_records} == {TRACE_REQUEST_ID}

    def test_api_and_worker_share_the_same_request_id(self, api_client, user, trace_records):
        """The literal epic DoD: one ID across the API layer and the worker."""
        response = _schedule_immediate(api_client, user, request_id=TRACE_REQUEST_ID)
        assert response.status_code == 200

        task = Task.objects.get(id=response.data["task_id"])
        assert task.request_id == TRACE_REQUEST_ID

        api_phase_records = list(trace_records)
        # Any records emitted while handling the request carry the same ID.
        for record in api_phase_records:
            assert record.request_id == TRACE_REQUEST_ID

        payload = _submit_and_capture_payload(task)
        trace_records.clear()
        result = execute_db_task(**payload)
        assert result["status"] == "success"

        worker_records = _worker_records(trace_records)
        assert worker_records, "worker emitted no log records"
        # API layer (response header, Task row, any request-phase records) and
        # the worker all agree on exactly one request ID.
        assert {r.request_id for r in worker_records} == {TRACE_REQUEST_ID}
        assert response["X-Request-ID"] == task.request_id == TRACE_REQUEST_ID

    def test_generated_request_id_when_header_absent(self, api_client, user, trace_records):
        response = _schedule_immediate(api_client, user)
        assert response.status_code == 200

        generated = response["X-Request-ID"]
        assert generated and generated != TRACE_REQUEST_ID
        # A valid UUID was generated, echoed, persisted...
        assert str(uuid.UUID(generated)) == generated

        task = Task.objects.get(id=response.data["task_id"])
        assert task.request_id == generated

        # ... and reaches the worker records.
        payload = _submit_and_capture_payload(task)
        trace_records.clear()
        assert execute_db_task(**payload)["status"] == "success"
        worker_records = _worker_records(trace_records)
        assert worker_records
        assert {r.request_id for r in worker_records} == {generated}

    def test_invalid_header_is_replaced(self, api_client, user, trace_records):
        response = _schedule_immediate(api_client, user, request_id="not-a-uuid")
        assert response.status_code == 200

        generated = response["X-Request-ID"]
        assert generated != "not-a-uuid"
        assert str(uuid.UUID(generated)) == generated

        task = Task.objects.get(id=response.data["task_id"])
        assert task.request_id == generated
        assert "not-a-uuid" not in {r.request_id for r in trace_records}

        payload = _submit_and_capture_payload(task)
        trace_records.clear()
        assert execute_db_task(**payload)["status"] == "success"
        worker_records = _worker_records(trace_records)
        assert worker_records
        # The attacker-controlled string never reaches the log output.
        assert {r.request_id for r in worker_records} == {generated}
        assert all("not-a-uuid" not in r.request_id for r in worker_records)

    def test_worker_falls_back_to_task_row(self, api_client, user, trace_records):
        """An old scheduler submits no request_id kwarg; the worker uses Task.request_id."""
        response = _schedule_immediate(api_client, user, request_id=TRACE_REQUEST_ID)
        assert response.status_code == 200
        task = Task.objects.get(id=response.data["task_id"])

        trace_records.clear()
        result = execute_db_task(task_id=task.id)
        assert result["status"] == "success"

        worker_records = _worker_records(trace_records)
        assert worker_records
        assert {r.request_id for r in worker_records} == {TRACE_REQUEST_ID}

    def test_no_request_context_yields_empty_id(self, user, trace_records):
        """A task with no request ID at all logs an empty ID, and does not crash."""
        task = Task.objects.create(
            name="cli-task",
            function_name="hello_world",
            task_data={},
            created_by=user,
        )
        assert task.request_id is None

        trace_records.clear()
        result = execute_db_task(task_id=task.id)
        assert result["status"] == "success"

        worker_records = _worker_records(trace_records)
        assert worker_records
        assert all(r.request_id == "" for r in worker_records)

    def test_retry_keeps_original_request_id(self, api_client, user, trace_records):
        """A retried task reuses its row, so retries keep the originating ID."""
        response = _schedule_immediate(api_client, user, request_id=TRACE_REQUEST_ID)
        task = Task.objects.get(id=response.data["task_id"])

        payload = _submit_and_capture_payload(task)
        trace_records.clear()
        assert execute_db_task(**payload)["status"] == "success"

        # Force a failed state so retry() accepts it, then retry and re-run.
        task.status = "failed"
        task.save(update_fields=["status"])
        assert task.retry()

        task.refresh_from_db()
        assert task.status == "pending"
        assert task.request_id == TRACE_REQUEST_ID

        payload = _submit_and_capture_payload(task)
        trace_records.clear()
        assert execute_db_task(**payload)["status"] == "success"

        worker_records = _worker_records(trace_records)
        assert worker_records
        assert {r.request_id for r in worker_records} == {TRACE_REQUEST_ID}


@pytest.mark.unit
@pytest.mark.django_db
class TestChainedTaskTraceContinuity:
    """A follow-on task created during a worker run inherits the request ID."""

    def test_chained_task_inherits_request_id(self, user, trace_records):
        summary_date = timezone.now().date() - timedelta(days=1)
        DailyMetricsSummary.objects.create(
            summary_date=summary_date,
            status="aggregated",
            aggregated_metrics={},
        )

        from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare

        with (
            patch("metrics_utility.anonymized_rollups.anonymize_rollups", return_value={}),
            request_context(TRACE_REQUEST_ID, origin="worker"),
        ):
            result = daily_anonymize_and_prepare(summary_date=str(summary_date))

        assert result["status"] == "success"

        follow_on = Task.objects.get(name=f"send_to_segment_{summary_date}")
        assert follow_on.function_name == "send_anonymized_to_segment"
        assert follow_on.request_id == TRACE_REQUEST_ID
