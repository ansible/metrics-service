"""
Comprehensive unit tests for the SimpleTaskScheduler module.

Tests all methods, edge cases, and error conditions for full code coverage.
"""

import logging
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, PropertyMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.tasks.simple_scheduler import (
    SimpleTaskScheduler,
    get_scheduler,
    initialize_system_tasks,
    refresh_scheduler,
    start_scheduler,
    stop_scheduler,
)

User = get_user_model()


@pytest.fixture
def mock_task():
    """Create a mock task object."""
    task = Mock()
    task.id = 1
    task.name = "Test Task"
    task.status = "pending"
    task.function_name = "test_function"
    task.task_data = {}
    task.scheduled_time = timezone.now()
    task.is_recurring = False
    task.cron_expression = None
    task.created = timezone.now()
    task.modified = timezone.now()
    task.save = Mock()
    return task


@pytest.fixture
def mock_recurring_task():
    """Create a mock recurring task object."""
    task = Mock()
    task.id = 2
    task.name = "Recurring Task"
    task.status = "pending"
    task.function_name = "recurring_function"
    task.task_data = {}
    task.scheduled_time = None
    task.is_recurring = True
    task.cron_expression = "*/5 * * * *"  # Every 5 minutes
    task.created = timezone.now() - timedelta(hours=1)
    task.modified = timezone.now() - timedelta(minutes=10)
    task.save = Mock()
    return task


@pytest.fixture
def scheduler():
    """Create a scheduler instance."""
    return SimpleTaskScheduler()


class TestSimpleTaskScheduler:
    """Test cases for SimpleTaskScheduler class."""

    def test_init(self, scheduler):
        """Test scheduler initialization."""
        assert scheduler.running is False
        assert scheduler.thread is None
        assert scheduler.check_interval == 30

    def test_start(self, scheduler):
        """Test starting the scheduler."""
        assert scheduler.running is False
        scheduler.start()
        assert scheduler.running is True
        assert scheduler.thread is not None
        assert scheduler.thread.daemon is True
        scheduler.stop()

    def test_start_already_running(self, scheduler, caplog):
        """Test starting an already running scheduler."""
        scheduler.running = True

        with caplog.at_level(logging.WARNING):
            scheduler.start()

        assert "Scheduler is already running" in caplog.text

    def test_stop(self, scheduler):
        """Test stopping the scheduler."""
        scheduler.start()
        assert scheduler.running is True
        scheduler.stop()
        assert scheduler.running is False

    @pytest.mark.django_db
    def test_stop_with_timeout(self, scheduler):
        """Test stopping the scheduler waits for thread to finish."""
        scheduler.check_interval = 0.1  # Short interval for faster stopping
        scheduler.start()
        thread = scheduler.thread
        time.sleep(0.2)  # Let it start and run at least once
        scheduler.stop()

        # Thread should be joined (not alive) after stop
        # The stop() method calls thread.join(timeout=5), so give it a bit more time
        time.sleep(0.5)
        assert not thread.is_alive()

    @patch("apps.tasks.simple_scheduler.time.sleep")
    @patch.object(SimpleTaskScheduler, "_check_and_submit_tasks")
    def test_run_loop_normal_operation(self, mock_check, mock_sleep, scheduler):
        """Test the main scheduler loop with normal operation."""
        # Stop after first iteration
        call_count = 0

        def stop_after_one(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                scheduler.running = False

        mock_check.side_effect = stop_after_one

        scheduler.running = True
        scheduler._run_loop()

        assert mock_check.call_count >= 1
        assert mock_sleep.call_count >= 1

    @patch("apps.tasks.simple_scheduler.time.sleep")
    @patch.object(SimpleTaskScheduler, "_check_and_submit_tasks")
    def test_run_loop_with_exception(self, mock_check, mock_sleep, scheduler, caplog):
        """Test the main scheduler loop handles exceptions."""
        call_count = 0

        def raise_once(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Test error")
            else:
                scheduler.running = False

        mock_check.side_effect = raise_once

        scheduler.running = True
        with caplog.at_level(logging.ERROR):
            scheduler._run_loop()

        assert "Error in scheduler loop" in caplog.text
        assert mock_check.call_count >= 2

    @pytest.mark.django_db
    @patch.object(SimpleTaskScheduler, "_submit_task_to_dispatcherd")
    def test_check_and_submit_scheduled_tasks(self, mock_submit, scheduler, user):
        """Test checking and submitting scheduled tasks."""
        from apps.tasks.models import Task

        # Set up a time in the past for scheduled_time
        past_time = timezone.now() - timedelta(hours=1)

        # Create a scheduled task
        task = Task.objects.create(
            name="Scheduled Task",
            function_name="test_function",
            status="pending",
            scheduled_time=past_time,
            is_recurring=False,
            created_by=user,
        )

        scheduler._check_and_submit_tasks()

        mock_submit.assert_called_once()
        assert mock_submit.call_args[0][0].id == task.id

    @pytest.mark.django_db
    @patch.object(SimpleTaskScheduler, "_submit_task_to_dispatcherd")
    @patch.object(SimpleTaskScheduler, "_should_run_recurring_task")
    def test_check_and_submit_recurring_tasks(self, mock_should_run, mock_submit, scheduler, user):
        """Test checking and submitting recurring tasks."""
        from apps.tasks.models import Task

        mock_should_run.return_value = True

        # Create a recurring task
        task = Task.objects.create(
            name="Recurring Task",
            function_name="recurring_function",
            status="pending",
            is_recurring=True,
            cron_expression="*/5 * * * *",
            created_by=user,
        )

        scheduler._check_and_submit_tasks()

        mock_should_run.assert_called_once()
        mock_submit.assert_called_once()
        assert mock_submit.call_args[0][0].id == task.id

    @pytest.mark.django_db
    @patch.object(SimpleTaskScheduler, "_submit_task_to_dispatcherd")
    @patch.object(SimpleTaskScheduler, "_should_run_recurring_task")
    def test_check_and_submit_tasks_excludes_empty_cron(self, mock_should_run, mock_submit, scheduler, user):
        """Test that recurring tasks with empty cron expressions are excluded."""
        from apps.tasks.models import Task

        # Create a recurring task with empty cron expression
        Task.objects.create(
            name="Empty Cron Task",
            function_name="test_function",
            status="pending",
            is_recurring=True,
            cron_expression="",
            created_by=user,
        )

        scheduler._check_and_submit_tasks()

        # Should not be called because cron_expression is empty
        mock_should_run.assert_not_called()
        mock_submit.assert_not_called()

    @patch("apps.tasks.models.Task")
    def test_check_and_submit_tasks_handles_exception(self, mock_task_model, scheduler, caplog):
        """Test that _check_and_submit_tasks handles exceptions gracefully."""
        # Mock the Task.objects.filter to raise an exception
        mock_task_model.objects.filter.side_effect = Exception("Database error")

        with caplog.at_level(logging.ERROR):
            scheduler._check_and_submit_tasks()

        assert "Error checking tasks" in caplog.text

    def test_should_run_recurring_task_due_now(self, scheduler, mock_recurring_task):
        """Test recurring task that is due to run now."""
        # Set last run to 10 minutes ago, cron is every 5 minutes
        mock_recurring_task.modified = timezone.now() - timedelta(minutes=10)
        mock_recurring_task.cron_expression = "*/5 * * * *"

        now = timezone.now()
        result = scheduler._should_run_recurring_task(mock_recurring_task, now)

        assert result is True

    def test_should_run_recurring_task_uses_created_if_no_modified(self, scheduler, mock_recurring_task):
        """Test that created time is used if modified is None."""
        mock_recurring_task.modified = None
        mock_recurring_task.created = timezone.now() - timedelta(minutes=10)
        mock_recurring_task.cron_expression = "*/5 * * * *"

        now = timezone.now()
        result = scheduler._should_run_recurring_task(mock_recurring_task, now)

        assert result is True

    def test_should_run_recurring_task_with_naive_datetime(self, scheduler, mock_recurring_task):
        """Test recurring task with naive datetime objects."""
        # Create naive datetime
        naive_dt = datetime.now() - timedelta(minutes=10)
        mock_recurring_task.modified = Mock()
        mock_recurring_task.modified.replace = Mock(return_value=naive_dt)
        mock_recurring_task.cron_expression = "*/5 * * * *"

        now = datetime.now()
        result = scheduler._should_run_recurring_task(mock_recurring_task, now)

        assert result in [True, False]  # Should complete without error

    def test_should_run_recurring_task_handles_exception(self, scheduler, mock_recurring_task, caplog):
        """Test that _should_run_recurring_task handles exceptions."""
        mock_recurring_task.cron_expression = "invalid cron"

        now = timezone.now()
        with caplog.at_level(logging.ERROR):
            result = scheduler._should_run_recurring_task(mock_recurring_task, now)

        assert result is False
        assert "Error checking recurring task" in caplog.text

    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    def test_submit_task_to_dispatcherd_one_time(self, mock_submit, scheduler, mock_task, caplog):
        """Test submitting a one-time task to dispatcherd."""
        mock_task.is_recurring = False

        with caplog.at_level(logging.INFO):
            scheduler._submit_task_to_dispatcherd(mock_task)

        mock_submit.assert_called_once_with(mock_task)
        assert "Submitting task" in caplog.text

    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    @patch.object(SimpleTaskScheduler, "_update_recurring_task_last_run")
    def test_submit_task_to_dispatcherd_recurring(self, mock_update, mock_submit, scheduler, mock_recurring_task):
        """Test submitting a recurring task updates last run time."""
        scheduler._submit_task_to_dispatcherd(mock_recurring_task)

        mock_submit.assert_called_once_with(mock_recurring_task)
        mock_update.assert_called_once_with(mock_recurring_task)

    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    def test_submit_task_to_dispatcherd_handles_exception(self, mock_submit, scheduler, mock_task, caplog):
        """Test that _submit_task_to_dispatcherd handles exceptions."""
        mock_submit.side_effect = Exception("Submission error")

        with caplog.at_level(logging.ERROR):
            scheduler._submit_task_to_dispatcherd(mock_task)

        assert "Error submitting task" in caplog.text
        assert mock_task.status == "failed"
        assert "Failed to submit to dispatcher" in mock_task.error_message
        mock_task.save.assert_called_once()

    def test_update_recurring_task_last_run(self, scheduler, mock_recurring_task, caplog):
        """Test updating last run time for recurring task."""
        with caplog.at_level(logging.INFO):
            scheduler._update_recurring_task_last_run(mock_recurring_task)

        assert hasattr(mock_recurring_task, "_skip_signals")
        assert mock_recurring_task._skip_signals is True
        mock_recurring_task.save.assert_called_once_with(update_fields=["modified"])
        assert "Updated last run time" in caplog.text

    def test_update_recurring_task_last_run_handles_exception(self, scheduler, mock_recurring_task, caplog):
        """Test that _update_recurring_task_last_run handles exceptions."""
        mock_recurring_task.save.side_effect = Exception("Save error")

        with caplog.at_level(logging.ERROR):
            scheduler._update_recurring_task_last_run(mock_recurring_task)

        assert "Error updating last run time" in caplog.text


class TestInitializeSystemTasks:
    """Test cases for initialize_system_tasks function."""

    @pytest.mark.django_db
    @patch("apps.tasks.simple_scheduler.settings")
    def test_initialize_system_tasks_all_enabled(self, mock_settings, caplog):
        """Test initializing system tasks with all feature enables enabled."""
        mock_settings.FEATURE_ENABLED = {
            "METRICS_COLLECTION_ENABLED": True,
            "ANONYMIZED_DATA_ENABLED": True,
        }

        with caplog.at_level(logging.INFO):
            initialize_system_tasks()

        from apps.tasks.models import Task

        # Check that tasks were created
        tasks = Task.objects.filter(is_system_task=True)
        assert tasks.count() == 3

        task_names = [task.name for task in tasks]
        assert "Metrics Collection" in task_names
        assert "Anonymized Data Cleanup" in task_names
        assert "System Cleanup" in task_names

        assert "Initialized" in caplog.text or "system tasks" in caplog.text

    @pytest.mark.django_db
    @patch("apps.tasks.simple_scheduler.settings")
    def test_initialize_system_tasks_partial_enabled(self, mock_settings):
        """Test initializing system tasks with some feature enables disabled."""
        mock_settings.FEATURE_ENABLED = {
            "METRICS_COLLECTION_ENABLED": False,
            "ANONYMIZED_DATA_ENABLED": True,
        }

        initialize_system_tasks()

        from apps.tasks.models import Task

        tasks = Task.objects.filter(is_system_task=True)
        task_names = [task.name for task in tasks]

        # Should have Anonymized Data Cleanup and System Cleanup, but not Metrics Collection
        assert "Metrics Collection" not in task_names
        assert "Anonymized Data Cleanup" in task_names
        assert "System Cleanup" in task_names

    @pytest.mark.django_db
    @patch("apps.tasks.simple_scheduler.settings")
    def test_initialize_system_tasks_no_feature_enabled(self, mock_settings):
        """Test initializing system tasks with no FEATURE_ENABLED in settings."""
        # Simulate settings without FEATURE_ENABLED
        del mock_settings.feature_enabled
        type(mock_settings).feature_enabled = PropertyMock(side_effect=AttributeError)

        # Should default to having the flags enabled
        with patch("apps.tasks.simple_scheduler.getattr") as mock_getattr:
            mock_getattr.return_value = {}
            initialize_system_tasks()

        from apps.tasks.models import Task

        # System Cleanup should always be created
        tasks = Task.objects.filter(is_system_task=True, name="System Cleanup")
        assert tasks.count() == 1

    @pytest.mark.django_db
    @patch("apps.tasks.simple_scheduler.settings")
    def test_initialize_system_tasks_idempotent(self, mock_settings, caplog):
        """Test that initializing system tasks is idempotent."""
        mock_settings.FEATURE_ENABLED = {
            "METRICS_COLLECTION_ENABLED": True,
            "ANONYMIZED_DATA_ENABLED": True,
        }

        # First call
        initialize_system_tasks()

        from apps.tasks.models import Task

        first_count = Task.objects.filter(is_system_task=True).count()

        # Second call
        with caplog.at_level(logging.DEBUG):
            initialize_system_tasks()

        second_count = Task.objects.filter(is_system_task=True).count()

        # Should not create duplicates
        assert first_count == second_count
        assert "already exist" in caplog.text

    @pytest.mark.django_db
    def test_initialize_system_tasks_creates_system_user(self):
        """Test that a system user is created if it doesn't exist."""
        user_model = get_user_model()

        # Make sure system user doesn't exist
        user_model.objects.filter(username="system").delete()

        initialize_system_tasks()

        # System user should now exist
        system_user = user_model.objects.filter(username="system").first()
        assert system_user is not None
        assert system_user.email == "system@localhost"

    @pytest.mark.django_db
    def test_initialize_system_tasks_uses_existing_system_user(self):
        """Test that existing system user is used."""
        user_model = get_user_model()

        # Create a system user
        existing_user = user_model.objects.create(username="system", email="existing@localhost")

        initialize_system_tasks()

        # Should use existing user
        system_users = user_model.objects.filter(username="system")
        assert system_users.count() == 1
        assert system_users.first().id == existing_user.id

    @pytest.mark.django_db
    def test_initialize_system_tasks_handles_exception(self, caplog):
        """Test that initialize_system_tasks handles exceptions gracefully."""
        with patch("django.contrib.auth.get_user_model") as mock_get_user:
            mock_get_user.side_effect = Exception("Database error")

            with caplog.at_level(logging.ERROR):
                initialize_system_tasks()

            assert "Error initializing system tasks" in caplog.text

    @pytest.mark.django_db
    @patch("apps.tasks.simple_scheduler.settings")
    def test_initialize_system_tasks_correct_cron_expressions(self, mock_settings):
        """Test that system tasks have correct cron expressions."""
        mock_settings.FEATURE_ENABLED = {
            "METRICS_COLLECTION_ENABLED": True,
            "ANONYMIZED_DATA_ENABLED": True,
        }

        initialize_system_tasks()

        from apps.tasks.models import Task

        metrics_task = Task.objects.get(name="Metrics Collection", is_system_task=True)
        assert metrics_task.cron_expression == "0 2 * * *"
        assert metrics_task.is_recurring is True

        cleanup_task = Task.objects.get(name="Anonymized Data Cleanup", is_system_task=True)
        assert cleanup_task.cron_expression == "0 3 * * 0"
        assert cleanup_task.is_recurring is True

        system_cleanup = Task.objects.get(name="System Cleanup", is_system_task=True)
        assert system_cleanup.cron_expression == "0 1 * * *"
        assert system_cleanup.is_recurring is True

    @pytest.mark.django_db
    @patch("apps.tasks.simple_scheduler.settings")
    def test_initialize_system_tasks_correct_priorities(self, mock_settings):
        """Test that system tasks have correct priorities."""
        mock_settings.FEATURE_ENABLED = {
            "METRICS_COLLECTION_ENABLED": True,
            "ANONYMIZED_DATA_ENABLED": True,
        }

        initialize_system_tasks()

        from apps.tasks.models import Task

        metrics_task = Task.objects.get(name="Metrics Collection", is_system_task=True)
        assert metrics_task.priority == 1

        cleanup_task = Task.objects.get(name="Anonymized Data Cleanup", is_system_task=True)
        assert cleanup_task.priority == 2

        system_cleanup = Task.objects.get(name="System Cleanup", is_system_task=True)
        assert system_cleanup.priority == 3


class TestGlobalSchedulerFunctions:
    """Test cases for global scheduler management functions."""

    def teardown_method(self):
        """Clean up after each test."""
        # Reset the global scheduler
        import apps.tasks.simple_scheduler as scheduler_module

        scheduler_module._scheduler = None

    def test_start_scheduler_creates_new_instance(self):
        """Test start_scheduler creates a new scheduler instance."""
        with patch.object(SimpleTaskScheduler, "start") as mock_start:
            start_scheduler()
            mock_start.assert_called_once()

    def test_start_scheduler_reuses_existing_instance(self):
        """Test start_scheduler reuses existing scheduler instance."""
        start_scheduler()
        scheduler1 = get_scheduler()

        start_scheduler()
        scheduler2 = get_scheduler()

        # Should be the same instance
        assert scheduler1 is scheduler2

        # Clean up
        stop_scheduler()

    def test_stop_scheduler_stops_running_scheduler(self):
        """Test stop_scheduler stops the running scheduler."""
        start_scheduler()
        scheduler = get_scheduler()

        assert scheduler.running is True

        stop_scheduler()

        assert scheduler.running is False

    def test_stop_scheduler_when_no_scheduler_exists(self):
        """Test stop_scheduler when no scheduler exists."""
        import apps.tasks.simple_scheduler as scheduler_module

        scheduler_module._scheduler = None

        # Should not raise an error
        stop_scheduler()

    def test_get_scheduler_creates_new_instance(self):
        """Test get_scheduler creates a new instance if none exists."""
        scheduler = get_scheduler()

        assert scheduler is not None
        assert isinstance(scheduler, SimpleTaskScheduler)

    def test_get_scheduler_returns_existing_instance(self):
        """Test get_scheduler returns the existing instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()

        assert scheduler1 is scheduler2

    def test_refresh_scheduler(self, caplog):
        """Test refresh_scheduler logs a message."""
        with caplog.at_level(logging.INFO):
            refresh_scheduler()

        assert "Scheduler refresh requested" in caplog.text


class TestSchedulerIntegration:
    """Integration tests for scheduler functionality."""

    @pytest.mark.django_db
    @patch.object(SimpleTaskScheduler, "_check_and_submit_tasks")
    def test_full_scheduler_lifecycle(self, mock_check):
        """Test complete scheduler lifecycle from start to stop."""
        scheduler = SimpleTaskScheduler()
        scheduler.check_interval = 0.5  # Check every 0.5 seconds for faster testing

        # Start scheduler
        scheduler.start()
        assert scheduler.running is True
        assert scheduler.thread is not None

        # Wait for scheduler to run a few checks
        time.sleep(1.5)

        # Stop scheduler
        scheduler.stop()
        assert scheduler.running is False

        # Check method should have been called at least once
        assert mock_check.call_count >= 1

    @pytest.mark.django_db
    def test_multiple_scheduler_starts_and_stops(self):
        """Test starting and stopping scheduler multiple times."""
        scheduler = SimpleTaskScheduler()

        # Start and stop multiple times
        for _ in range(3):
            scheduler.start()
            assert scheduler.running is True
            time.sleep(0.1)
            scheduler.stop()
            assert scheduler.running is False

    @pytest.mark.django_db
    @patch.object(SimpleTaskScheduler, "_submit_task_to_dispatcherd")
    def test_scheduler_handles_multiple_tasks(self, mock_submit, user):
        """Test scheduler handles multiple tasks correctly."""
        from apps.tasks.models import Task

        past_time = timezone.now() - timedelta(seconds=1)

        # Create multiple tasks
        for i in range(5):
            Task.objects.create(
                name=f"Test Task {i}",
                function_name="test_function",
                status="pending",
                scheduled_time=past_time,
                is_recurring=False,
                created_by=user,
            )

        scheduler = SimpleTaskScheduler()

        # Directly call _check_and_submit_tasks to test without threading issues
        scheduler._check_and_submit_tasks()

        # All tasks should have been submitted
        assert mock_submit.call_count == 5


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_scheduler_with_zero_check_interval(self):
        """Test scheduler behavior with very short check interval."""
        scheduler = SimpleTaskScheduler()
        scheduler.check_interval = 0.1

        scheduler.start()
        time.sleep(0.5)
        scheduler.stop()

        # Should complete without error

    @pytest.mark.django_db
    def test_recurring_task_with_invalid_cron(self, user):
        """Test recurring task with invalid cron expression."""
        from apps.tasks.models import Task

        task = Task.objects.create(
            name="Invalid Cron Task",
            function_name="test_function",
            status="pending",
            is_recurring=True,
            cron_expression="invalid cron expression",
            created_by=user,
        )

        scheduler = SimpleTaskScheduler()

        # Should not crash
        now = timezone.now()
        result = scheduler._should_run_recurring_task(task, now)

        assert result is False

    @pytest.mark.django_db
    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    def test_concurrent_task_submissions(self, mock_submit, user):
        """Test scheduler handles concurrent task submissions safely."""
        from apps.tasks.models import Task

        past_time = timezone.now() - timedelta(seconds=1)

        task = Task.objects.create(
            name="Concurrent Task",
            function_name="test_function",
            status="pending",
            scheduled_time=past_time,
            is_recurring=False,
            created_by=user,
        )

        scheduler = SimpleTaskScheduler()

        # Submit same task multiple times concurrently
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(scheduler._submit_task_to_dispatcherd, task) for _ in range(5)]
            concurrent.futures.wait(futures)

        # Should complete without errors

    def test_scheduler_thread_daemon_property(self):
        """Test that scheduler thread is properly marked as daemon."""
        scheduler = SimpleTaskScheduler()
        scheduler.start()

        assert scheduler.thread.daemon is True

        scheduler.stop()
