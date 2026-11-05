"""
Tier 2 trace-continuity tests (AAP-79590): the scheduler is in the loop.

Tier 1 (``test_trace_continuity.py``) submits via ``submit_task_to_dispatcher``
directly. These tests drive ``UnifiedTaskScheduler._execute_database_task()``
with real Task rows so the scheduler's own submit paths — both the
non-recurring and the recurring (execution-row) branch — are covered too.

The dispatcherd broker is still mocked at the
``apps.tasks.tasks_system.submit_task_to_dispatcher`` boundary (the scheduler
imports it lazily, so the patch takes effect).

``_execute_database_task`` opens with ``close_old_connections()``, which closes
the connection a wrapped (non-transactional) test is borrowing — hence the
``transaction=True`` marker: these tests need a real, committable connection.
"""

from unittest.mock import patch

import pytest

from apps.tasks.cron_scheduler import UnifiedTaskScheduler
from apps.tasks.models import Task
from tests.unit.tasks.conftest import TRACE_REQUEST_ID


def _make_task(**kwargs):
    defaults = {
        "name": "Trace Continuity Task",
        "function_name": "hello_world",
        "task_data": {},
        "status": "pending",
        "request_id": TRACE_REQUEST_ID,
    }
    defaults.update(kwargs)
    return Task.objects.create(**defaults)


@pytest.mark.unit
@pytest.mark.django_db(transaction=True)
class TestSchedulerTraceContinuity:
    """The scheduler submits tasks without losing their request ID."""

    def test_scheduler_submits_pending_task_with_request_id(self, user):
        task = _make_task(created_by=user)
        scheduler = UnifiedTaskScheduler()

        with patch("apps.tasks.tasks_system.submit_task_to_dispatcher") as submit:
            scheduler._execute_database_task(task.id)

        submit.assert_called_once()
        submitted = submit.call_args.args[0]
        assert submitted.id == task.id
        assert submitted.request_id == TRACE_REQUEST_ID

    def test_scheduler_recurring_execution_copies_request_id(self, user):
        """Each execution row of a recurring template carries the template's ID."""
        template = _make_task(
            name="Trace Recurring Template",
            cron_expression="0 3 * * *",
            created_by=user,
        )
        scheduler = UnifiedTaskScheduler()

        with patch("apps.tasks.tasks_system.submit_task_to_dispatcher") as submit:
            scheduler._execute_database_task(template.id)

        submit.assert_called_once()
        execution_task = submit.call_args.args[0]
        assert execution_task.id != template.id
        assert execution_task.cron_expression is None
        assert execution_task.request_id == TRACE_REQUEST_ID

        # The execution row is persisted with the copied ID.
        execution_row = Task.objects.get(id=execution_task.id)
        assert execution_row.request_id == TRACE_REQUEST_ID
        # The template is left unchanged for future executions.
        template.refresh_from_db()
        assert template.request_id == TRACE_REQUEST_ID
        assert template.cron_expression == "0 3 * * *"
