"""
Unit tests for apps/tasks/cleanup/cleanup_stuck_tasks.py

Tests cover:
- Dry run mode counts without modifying
- Stuck tasks (past their timeout) are marked failed
- Tasks still within their timeout are ignored
- Tasks with no started_at are ignored
- Associated TaskExecution records are also failed
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.tasks.cleanup.cleanup_stuck_tasks import cleanup_stuck_tasks


@pytest.mark.unit
@pytest.mark.django_db
class TestCleanupStuckTasks:
    """Test cleanup_stuck_tasks function."""

    def test_dry_run_counts_without_failing(self, user):
        """Test dry_run=True counts stuck tasks without modifying them."""
        from apps.tasks.models import Task

        # Create a task stuck in running for 2 hours (timeout is 3600s = 1 hour)
        task = Task.objects.create(
            name="Stuck Task",
            function_name="hello_world",
            task_data={},
            created_by=user,
            status="running",
        )
        Task.objects.filter(id=task.id).update(started_at=timezone.now() - timedelta(hours=2))

        result = cleanup_stuck_tasks(dry_run=True)

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["tasks_found"] == 1
        assert result["tasks_failed"] == 0

        # Verify task is still running
        assert Task.objects.get(id=task.id).status == "running"

    def test_fails_stuck_task(self, user):
        """Test that a task past its timeout is marked failed with completed_at and error_message set."""
        from apps.tasks.models import Task

        task = Task.objects.create(
            name="Stuck Task",
            function_name="hello_world",
            task_data={},
            created_by=user,
            status="running",
        )
        Task.objects.filter(id=task.id).update(started_at=timezone.now() - timedelta(hours=2))

        result = cleanup_stuck_tasks()

        assert result["status"] == "success"
        assert result["tasks_failed"] == 1

        task.refresh_from_db()
        assert task.status == "failed"
        assert task.completed_at is not None
        assert task.error_message != ""

    def test_ignores_task_within_timeout(self, user):
        """Test that a running task not yet past its timeout is left alone."""
        from apps.tasks.models import Task

        task = Task.objects.create(
            name="Running Task",
            function_name="hello_world",
            task_data={},
            created_by=user,
            status="running",
        )
        # started_at 10 minutes ago; default timeout is 3600s
        Task.objects.filter(id=task.id).update(started_at=timezone.now() - timedelta(minutes=10))

        result = cleanup_stuck_tasks()

        assert result["tasks_found"] == 0
        assert result["tasks_failed"] == 0
        assert Task.objects.get(id=task.id).status == "running"

    def test_ignores_task_with_no_started_at(self, running_task):
        """Test that a running task with no started_at is ignored."""
        from apps.tasks.models import Task

        # Ensure started_at is NULL
        Task.objects.filter(id=running_task.id).update(started_at=None)

        result = cleanup_stuck_tasks()

        assert result["tasks_found"] == 0
        assert Task.objects.get(id=running_task.id).status == "running"

    def test_fails_associated_task_execution(self, user):
        """Test that the running TaskExecution for a stuck task is also failed."""
        from apps.tasks.models import Task, TaskExecution

        task = Task.objects.create(
            name="Stuck Task",
            function_name="hello_world",
            task_data={},
            created_by=user,
            status="running",
        )
        Task.objects.filter(id=task.id).update(started_at=timezone.now() - timedelta(hours=2))
        task.refresh_from_db()

        execution = TaskExecution.objects.create(task=task, status="running")

        result = cleanup_stuck_tasks()

        assert result["executions_failed"] == 1

        execution.refresh_from_db()
        assert execution.status == "failed"
        assert execution.completed_at is not None

    def test_does_not_touch_completed_or_failed_tasks(self, old_completed_task, old_failed_task):
        """Test that already-completed or failed tasks are never touched."""
        result = cleanup_stuck_tasks()

        assert result["tasks_found"] == 0
        assert result["tasks_failed"] == 0

    def test_no_stuck_tasks_returns_zero_counts(self):
        """Test returns zeros when there are no stuck tasks."""
        result = cleanup_stuck_tasks()

        assert result["status"] == "success"
        assert result["tasks_found"] == 0
        assert result["tasks_failed"] == 0
        assert result["executions_found"] == 0
        assert result["executions_failed"] == 0
