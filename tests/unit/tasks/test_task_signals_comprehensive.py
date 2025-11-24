"""
Comprehensive tests for apps/tasks/signals.py

This module provides extensive test coverage for task signal handlers,
including immediate execution, scheduled tasks, and error conditions.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.core.models import User
from apps.tasks.models import Task
from apps.tasks.signals import (
    _handle_new_task,
    _handle_updated_task,
    _register_with_scheduler,
)
from tests.test_utils import get_test_password


@pytest.mark.unit
@pytest.mark.django_db
class TestTaskSignalHandlers(TestCase):
    """Test task signal handlers."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def _create_task_without_signals(self, **kwargs):
        """Create a task without triggering signals."""
        defaults = {
            "name": "Test Task",
            "function_name": "cleanup_old_data",
            "created_by": self.user,
            "status": "pending",
        }
        defaults.update(kwargs)

        task = Task(**defaults)
        task._skip_signals = True
        task.save()
        return task

    def test_task_created_signal_handler(self):
        """Test signal handler for task creation."""
        with (
            patch("apps.tasks.signals._handle_new_task") as mock_handle_new,
            patch("apps.tasks.signals._register_with_scheduler") as mock_register,
        ):
            # Create task normally to trigger signals
            task = Task.objects.create(name="Signal Test Task", function_name="cleanup_old_data", created_by=self.user)

            # Verify handlers were called
            mock_handle_new.assert_called_once_with(task)
            mock_register.assert_called_once_with(task, True)

    def test_task_updated_signal_handler(self):
        """Test signal handler for task updates."""
        # Create task without signals first
        task = self._create_task_without_signals()

        with (
            patch("apps.tasks.signals._handle_updated_task") as mock_handle_updated,
            patch("apps.tasks.signals._register_with_scheduler") as mock_register,
        ):
            # Update task to trigger signals
            task._skip_signals = False
            task.name = "Updated Task Name"
            task.save()

            # Verify handlers were called
            mock_handle_updated.assert_called_once_with(task)
            mock_register.assert_called_once_with(task, False)

    def test_signal_handler_skips_when_skip_signals_set(self):
        """Test that signal handler is skipped when _skip_signals is True."""
        with (
            patch("apps.tasks.signals._handle_new_task") as mock_handle_new,
            patch("apps.tasks.signals._register_with_scheduler") as mock_register,
        ):
            # Create task with _skip_signals = True
            task = Task(name="Skip Signals Task", function_name="cleanup_old_data", created_by=self.user)
            task._skip_signals = True
            task.save()

            # Handlers should not be called
            mock_handle_new.assert_not_called()
            mock_register.assert_not_called()

    @patch("apps.tasks.signals.logger")
    def test_signal_handler_logs_task_creation(self, mock_logger):
        """Test that signal handler logs task creation."""
        Task.objects.create(name="Log Test Task", function_name="cleanup_old_data", created_by=self.user)

        # Verify logging was called
        mock_logger.info.assert_called()
        log_call_args = mock_logger.info.call_args[0][0]
        assert "New task created" in log_call_args
        assert "Log Test Task" in log_call_args

    @patch("apps.tasks.signals.logger")
    def test_signal_handler_logs_task_update(self, mock_logger):
        """Test that signal handler logs task updates."""
        # Create task without signals first
        task = self._create_task_without_signals()

        # Clear any previous log calls
        mock_logger.reset_mock()

        # Update task to trigger signals
        task._skip_signals = False
        task.name = "Updated Log Test Task"
        task.save()

        # Verify logging was called
        mock_logger.info.assert_called()
        log_call_args = mock_logger.info.call_args[0][0]
        assert "Task updated" in log_call_args

    @patch("apps.tasks.signals.logger")
    def test_signal_handler_handles_exceptions(self, mock_logger):
        """Test that signal handler handles exceptions gracefully."""
        with patch("apps.tasks.signals._handle_new_task") as mock_handle:
            # Make _handle_new_task raise an exception
            mock_handle.side_effect = Exception("Test exception")

            # Create task - should not raise exception
            Task.objects.create(name="Exception Test Task", function_name="cleanup_old_data", created_by=self.user)

            # Verify error was logged
            mock_logger.error.assert_called()
            error_call_args = mock_logger.error.call_args[0][0]
            assert "Error in task signal handler" in error_call_args
            assert "Test exception" in error_call_args

    def test_task_deleted_signal_handler(self):
        """Test signal handler for task deletion."""
        # Create task first
        task = self._create_task_without_signals(name="Delete Test Task")
        task_name = task.name

        with (
            patch("apps.tasks.signals._unregister_from_scheduler") as mock_unregister,
            patch("apps.tasks.signals.logger") as mock_logger,
        ):
            # Delete task to trigger signal
            task.delete()

            # Verify unregister was called
            mock_unregister.assert_called_once()

            # Verify logging
            mock_logger.info.assert_called()
            log_call_args = mock_logger.info.call_args[0][0]
            assert "Task deleted" in log_call_args
            assert task_name in log_call_args


@pytest.mark.unit
@pytest.mark.django_db
class TestHandleNewTask(TestCase):
    """Test _handle_new_task function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def _create_task_without_signals(self, **kwargs):
        """Create a task without triggering signals."""
        defaults = {
            "name": "Test Task",
            "function_name": "cleanup_old_data",
            "created_by": self.user,
            "status": "pending",
        }
        defaults.update(kwargs)

        task = Task(**defaults)
        task._skip_signals = True
        task.save()
        return task

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    def test_handle_new_task_immediate_execution(self, mock_submit):
        """Test handling new task for immediate execution."""
        # Create task ready for immediate execution
        task = self._create_task_without_signals(status="pending", scheduled_time=None)

        with patch.object(task, "is_ready_to_run", return_value=True):
            _handle_new_task(task)

            # Should submit to dispatcher
            mock_submit.assert_called_once_with(task)

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    def test_handle_new_task_not_ready(self, mock_submit):
        """Test handling new task that's not ready to run."""
        # Create task not ready for execution
        task = self._create_task_without_signals(status="draft")

        with patch.object(task, "is_ready_to_run", return_value=False):
            _handle_new_task(task)

            # Should not submit to dispatcher
            mock_submit.assert_not_called()

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    def test_handle_new_task_scheduled_future(self, mock_submit):
        """Test handling new task scheduled for future execution."""
        # Create task with future scheduled time
        future_time = timezone.now() + timedelta(hours=1)
        task = self._create_task_without_signals(status="pending", scheduled_time=future_time)

        with patch.object(task, "is_ready_to_run", return_value=True):
            _handle_new_task(task)

            # Should not submit to dispatcher (will be handled by scheduler)
            mock_submit.assert_not_called()

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    def test_handle_new_task_recurring(self, mock_submit):
        """Test handling new recurring task."""
        # Create recurring task
        task = self._create_task_without_signals(status="pending", is_recurring=True, cron_schedule="0 2 * * *")

        with patch.object(task, "is_ready_to_run", return_value=True):
            _handle_new_task(task)

            # Should not submit to dispatcher (will be handled by scheduler)
            mock_submit.assert_not_called()

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    @patch("apps.tasks.signals.logger")
    def test_handle_new_task_submission_error(self, mock_logger, mock_submit):
        """Test handling submission error for new task."""
        # Make submission raise an exception
        mock_submit.side_effect = Exception("Submission failed")

        task = self._create_task_without_signals(status="pending")

        with patch.object(task, "is_ready_to_run", return_value=True):
            _handle_new_task(task)

            # Should log the error
            mock_logger.error.assert_called()


@pytest.mark.unit
@pytest.mark.django_db
class TestHandleUpdatedTask(TestCase):
    """Test _handle_updated_task function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def _create_task_without_signals(self, **kwargs):
        """Create a task without triggering signals."""
        defaults = {
            "name": "Test Task",
            "function_name": "cleanup_old_data",
            "created_by": self.user,
            "status": "pending",
        }
        defaults.update(kwargs)

        task = Task(**defaults)
        task._skip_signals = True
        task.save()
        return task

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    def test_handle_updated_task_status_change_to_pending(self, mock_submit):
        """Test handling task update when status changes to pending."""
        task = self._create_task_without_signals(status="draft")

        # Change status to pending
        task.status = "pending"

        with patch.object(task, "is_ready_to_run", return_value=True):
            _handle_updated_task(task)

            # Should submit to dispatcher if now ready
            mock_submit.assert_called_once_with(task)

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    def test_handle_updated_task_not_ready_to_run(self, mock_submit):
        """Test handling task update when task is not ready to run."""
        task = self._create_task_without_signals(status="completed")

        with patch.object(task, "is_ready_to_run", return_value=False):
            _handle_updated_task(task)

            # Should not submit to dispatcher
            mock_submit.assert_not_called()

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    def test_handle_updated_task_with_scheduled_time(self, mock_submit):
        """Test handling task update with scheduled time."""
        future_time = timezone.now() + timedelta(hours=1)
        task = self._create_task_without_signals(status="pending", scheduled_time=future_time)

        with patch.object(task, "is_ready_to_run", return_value=True):
            _handle_updated_task(task)

            # Should not submit to dispatcher for scheduled tasks
            mock_submit.assert_not_called()

    @patch("apps.tasks.signals.cancel_task_in_dispatcherd")
    def test_handle_updated_task_status_change_to_cancelled(self, mock_cancel):
        """Test handling task update when status changes to cancelled."""
        task = self._create_task_without_signals(status="pending")

        # Change status to cancelled
        task.status = "cancelled"

        _handle_updated_task(task)

        # Should cancel in dispatcher
        mock_cancel.assert_called_once_with(task.id)

    @patch("apps.tasks.signals.cancel_task_in_dispatcherd")
    def test_handle_updated_task_status_change_to_failed(self, mock_cancel):
        """Test handling task update when status changes to failed."""
        task = self._create_task_without_signals(status="running")

        # Change status to failed
        task.status = "failed"

        _handle_updated_task(task)

        # Should not cancel (task already completed)
        mock_cancel.assert_not_called()


@pytest.mark.unit
@pytest.mark.django_db
class TestRegisterWithScheduler(TestCase):
    """Test _register_with_scheduler function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def _create_task_without_signals(self, **kwargs):
        """Create a task without triggering signals."""
        defaults = {"name": "Test Task", "function_name": "cleanup_old_data", "created_by": self.user}
        defaults.update(kwargs)

        task = Task(**defaults)
        task._skip_signals = True
        task.save()
        return task

    @patch("apps.tasks.signals.get_task_scheduler")
    def test_register_scheduled_task_with_scheduler(self, mock_get_scheduler):
        """Test registering scheduled task with scheduler."""
        mock_scheduler = MagicMock()
        mock_get_scheduler.return_value = mock_scheduler

        # Create task with future scheduled time
        future_time = timezone.now() + timedelta(hours=1)
        task = self._create_task_without_signals(scheduled_time=future_time, status="pending")

        _register_with_scheduler(task, created=True)

        # Should schedule the task
        mock_scheduler.schedule_task.assert_called_once_with(task)

    @patch("apps.tasks.signals.get_task_scheduler")
    def test_register_recurring_task_with_scheduler(self, mock_get_scheduler):
        """Test registering recurring task with scheduler."""
        mock_scheduler = MagicMock()
        mock_get_scheduler.return_value = mock_scheduler

        # Create recurring task
        task = self._create_task_without_signals(is_recurring=True, cron_schedule="0 2 * * *", status="pending")

        _register_with_scheduler(task, created=True)

        # Should register as recurring task
        mock_scheduler.schedule_recurring_task.assert_called_once_with(task)

    @patch("apps.tasks.signals.get_task_scheduler")
    def test_register_immediate_task_not_with_scheduler(self, mock_get_scheduler):
        """Test that immediate tasks are not registered with scheduler."""
        mock_scheduler = MagicMock()
        mock_get_scheduler.return_value = mock_scheduler

        # Create immediate task
        task = self._create_task_without_signals(scheduled_time=None, is_recurring=False, status="pending")

        _register_with_scheduler(task, created=True)

        # Should not register with scheduler
        mock_scheduler.schedule_task.assert_not_called()
        mock_scheduler.schedule_recurring_task.assert_not_called()

    @patch("apps.tasks.signals.get_task_scheduler")
    def test_register_task_update_reschedules(self, mock_get_scheduler):
        """Test that task updates reschedule with scheduler."""
        mock_scheduler = MagicMock()
        mock_get_scheduler.return_value = mock_scheduler

        # Create task with scheduled time
        future_time = timezone.now() + timedelta(hours=2)
        task = self._create_task_without_signals(scheduled_time=future_time, status="pending")

        _register_with_scheduler(task, created=False)

        # Should unregister old and register new
        mock_scheduler.unregister_task.assert_called_once_with(task.id)
        mock_scheduler.schedule_task.assert_called_once_with(task)

    @patch("apps.tasks.signals.get_task_scheduler")
    @patch("apps.tasks.signals.logger")
    def test_register_with_scheduler_handles_exceptions(self, mock_logger, mock_get_scheduler):
        """Test that scheduler registration handles exceptions."""
        mock_scheduler = MagicMock()
        mock_scheduler.schedule_task.side_effect = Exception("Scheduler error")
        mock_get_scheduler.return_value = mock_scheduler

        future_time = timezone.now() + timedelta(hours=1)
        task = self._create_task_without_signals(scheduled_time=future_time, status="pending")

        _register_with_scheduler(task, created=True)

        # Should log the error
        mock_logger.error.assert_called()
        error_call_args = mock_logger.error.call_args[0][0]
        assert "Error registering task with scheduler" in error_call_args


@pytest.mark.unit
@pytest.mark.django_db
class TestSignalIntegration(TestCase):
    """Test signal integration with actual task operations."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    @patch("apps.tasks.signals.get_task_scheduler")
    def test_end_to_end_task_creation_workflow(self, mock_get_scheduler, mock_submit):
        """Test complete workflow from task creation to execution."""
        mock_scheduler = MagicMock()
        mock_get_scheduler.return_value = mock_scheduler

        # Create immediate execution task
        task = Task.objects.create(
            name="E2E Test Task",
            function_name="cleanup_old_data",
            created_by=self.user,
            status="pending",
            task_data={"days_old": 30},
        )

        # Verify immediate submission
        mock_submit.assert_called_once_with(task)
        # Should not register with scheduler for immediate tasks
        mock_scheduler.schedule_task.assert_not_called()

    @patch("apps.tasks.signals.submit_task_to_dispatcherd")
    @patch("apps.tasks.signals.get_task_scheduler")
    def test_end_to_end_scheduled_task_workflow(self, mock_get_scheduler, mock_submit):
        """Test complete workflow for scheduled task."""
        mock_scheduler = MagicMock()
        mock_get_scheduler.return_value = mock_scheduler

        # Create scheduled task
        future_time = timezone.now() + timedelta(hours=1)
        task = Task.objects.create(
            name="Scheduled E2E Task",
            function_name="send_notification_email",
            created_by=self.user,
            status="pending",
            scheduled_time=future_time,
        )

        # Should not submit immediately
        mock_submit.assert_not_called()
        # Should register with scheduler
        mock_scheduler.schedule_task.assert_called_once_with(task)

    @patch("apps.tasks.signals.get_task_scheduler")
    def test_end_to_end_recurring_task_workflow(self, mock_get_scheduler):
        """Test complete workflow for recurring task."""
        mock_scheduler = MagicMock()
        mock_get_scheduler.return_value = mock_scheduler

        # Create recurring task
        task = Task.objects.create(
            name="Recurring E2E Task",
            function_name="cleanup_old_data",
            created_by=self.user,
            status="pending",
            is_recurring=True,
            cron_schedule="0 2 * * *",
        )

        # Should register as recurring with scheduler
        mock_scheduler.schedule_recurring_task.assert_called_once_with(task)

    @patch("apps.tasks.signals._unregister_from_scheduler")
    def test_end_to_end_task_deletion_workflow(self, mock_unregister):
        """Test complete workflow for task deletion."""
        # Create and then delete task
        task = Task.objects.create(name="Delete E2E Task", function_name="cleanup_old_data", created_by=self.user)

        # Delete the task
        task.delete()

        # Should unregister from scheduler
        mock_unregister.assert_called_once()

    def test_signal_performance_with_multiple_tasks(self):
        """Test signal performance with multiple task operations."""
        import time

        start_time = time.time()

        # Create multiple tasks
        tasks = []
        for i in range(10):
            task = Task.objects.create(
                name=f"Performance Test Task {i}", function_name="cleanup_old_data", created_by=self.user
            )
            tasks.append(task)

        end_time = time.time()
        creation_time = end_time - start_time

        # Should complete within reasonable time
        assert creation_time < 5.0  # Less than 5 seconds for 10 tasks

        # Verify all tasks were created
        assert len(tasks) == 10
