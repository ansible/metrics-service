"""Tests for the shared stuck-task recovery helper."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.db.models.query import QuerySet
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.tasks.models import Task, TaskExecution
from apps.tasks.utils import STUCK_TASK_ERROR_MESSAGE, fail_stuck_tasks

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _task(name, *, status="running", started_at=None, **kwargs):
    return Task.objects.create(
        name=name,
        function_name="hello_world",
        task_data={},
        status=status,
        started_at=started_at,
        **kwargs,
    )


def test_fails_overdue_running_task_and_execution():
    now = timezone.now()
    task = _task("overdue", started_at=now - timedelta(hours=2))
    execution = TaskExecution.objects.create(task=task, status="running")

    failed_ids = fail_stuck_tasks(Task.objects.filter(pk=task.pk), now, timeout_seconds=60)

    assert failed_ids == [task.id]
    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "failed"
    assert task.error_message == STUCK_TASK_ERROR_MESSAGE
    assert task.completed_at == now
    assert execution.status == "failed"
    assert execution.error_message == STUCK_TASK_ERROR_MESSAGE
    assert execution.completed_at == now


def test_leaves_fresh_or_completed_tasks_untouched():
    now = timezone.now()
    fresh = _task("fresh", started_at=now)
    completed = _task("completed", status="completed", started_at=now - timedelta(hours=2))

    assert fail_stuck_tasks(Task.objects.filter(pk__in=[fresh.pk, completed.pk]), now, timeout_seconds=60) == []

    fresh.refresh_from_db()
    completed.refresh_from_db()
    assert fresh.status == "running"
    assert completed.status == "completed"


def test_updates_executions_before_tasks():
    """TaskExecution is updated first to match the scheduler recovery lock order."""
    now = timezone.now()
    task = _task("ordered", started_at=now - timedelta(hours=2))
    TaskExecution.objects.create(task=task, status="running")

    with CaptureQueriesContext(connection) as queries:
        fail_stuck_tasks(Task.objects.filter(pk=task.pk), now, timeout_seconds=60)

    update_tables = [
        "tasks_taskexecution" if "tasks_taskexecution" in query["sql"] else "tasks_task"
        for query in queries.captured_queries
        if query["sql"].startswith("UPDATE")
    ]
    assert update_tables == ["tasks_taskexecution", "tasks_task"]


def test_empty_queryset_returns_no_failed_ids():
    assert fail_stuck_tasks(Task.objects.none(), timezone.now(), timeout_seconds=60) == []


def test_multiple_stuck_tasks_are_all_failed():
    now = timezone.now()
    stuck = [_task(f"stuck-{index}", started_at=now - timedelta(hours=2)) for index in range(3)]

    failed_ids = fail_stuck_tasks(Task.objects.all(), now, timeout_seconds=60)

    assert sorted(failed_ids) == sorted(task.id for task in stuck)
    assert set(Task.objects.filter(status="failed").values_list("id", flat=True)) == {task.id for task in stuck}


def test_returns_empty_when_task_update_loses_race():
    """A concurrent recovery that wins the Task UPDATE must not report IDs as failed."""
    now = timezone.now()
    task = _task("raced", started_at=now - timedelta(hours=2))
    real_update = QuerySet.update

    def fake_update(queryset, **kwargs):
        if queryset.model is Task:
            return 0
        return real_update(queryset, **kwargs)

    with patch.object(QuerySet, "update", fake_update):
        assert fail_stuck_tasks(Task.objects.filter(pk=task.pk), now, timeout_seconds=60) == []

    task.refresh_from_db()
    assert task.status == "running"
