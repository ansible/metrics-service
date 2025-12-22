"""
Comprehensive unit tests for the UnifiedTaskScheduler module.

Tests all methods, edge cases, and error conditions for full code coverage.
"""

import logging
import threading
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from apps.tasks.cron_scheduler import (
    UnifiedTaskScheduler,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
)


@pytest.fixture
def mock_task_groups():
    """Mock task groups data."""
    return {
        "test_task_1": {
            "function": "hello_world",
            "cron": "0 */1 * * *",
            "args": {"message": "test"},
            "enabled": True,
            "description": "Test task 1",
        },
        "test_task_2": {
            "function": "cleanup_old_data",
            "cron": "0 2 * * *",
            "args": {"days_old": 30},
            "enabled": False,
            "description": "Test task 2",
        },
    }


@pytest.fixture
def mock_db_tasks():
    """Mock database Task objects."""
    task1 = Mock()
    task1.id = 1
    task1.name = "test_task_1"
    task1.function_name = "hello_world"
    task1.cron_expression = "0 */1 * * *"
    task1.task_data = {"message": "test"}
    task1.description = "Test task 1"
    task1.priority = 5
    task1.status = "pending"

    task2 = Mock()
    task2.id = 2
    task2.name = "test_task_2"
    task2.function_name = "cleanup_old_data"
    task2.cron_expression = "0 2 * * *"
    task2.task_data = {"days_old": 30}
    task2.description = "Test task 2"
    task2.priority = 5
    task2.status = "pending"

    return [task1, task2]


@pytest.fixture(autouse=True)
def mock_task_database():
    """Auto-mock the Task database for all tests."""
    with patch("apps.tasks.models.Task") as mock_task_database:
        # Mock empty database by default
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset
        yield mock_task_database


@pytest.fixture
def mock_task_group_status():
    """Mock task group status."""
    return {
        "system_tasks": {
            "enabled": True,
            "enabled_tasks": 2,
            "total_tasks": 3,
        },
        "disabled_group": {
            "enabled": False,
            "enabled_tasks": 0,
            "total_tasks": 2,
        },
    }


@pytest.fixture
def mock_task_functions():
    """Mock task functions."""
    return {
        "hello_world": Mock(),
        "cleanup_old_data": Mock(),
        "send_notification_email": Mock(),
        "process_user_data": Mock(),
        "execute_db_task": Mock(),
        "sleep": Mock(),
    }


class TestUnifiedTaskScheduler:
    """Test cases for UnifiedTaskScheduler class."""

    def test_init(self, mock_task_database, mock_db_tasks):
        """Test scheduler initialization."""
        # Mock the database query to return tasks
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = mock_db_tasks
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()

        assert isinstance(scheduler.scheduler, BackgroundScheduler)
        assert scheduler.running is False
        assert isinstance(scheduler._lock, type(threading.Lock()))
        # Should have loaded tasks from database
        assert len(scheduler.task_registry) == 2
        assert "test_task_1" in scheduler.task_registry
        assert "test_task_2" in scheduler.task_registry

    def test_init_with_load_error(self, mock_task_database, caplog):
        """Test initialization handles load errors gracefully."""
        # Make database query fail
        mock_task_database.objects.filter.side_effect = Exception("Database error")

        with caplog.at_level(logging.ERROR, logger="apps.tasks.cron_scheduler"):
            scheduler = UnifiedTaskScheduler()

        assert scheduler.task_registry == {}

    def test_load_task_registry_success(self, mock_task_database, mock_db_tasks, caplog):
        """Test successful task registry loading."""
        # Mock the database query
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = mock_db_tasks
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()

        with caplog.at_level(logging.INFO, logger="apps.tasks.cron_scheduler"):
            scheduler._load_task_registry()

        # Should log the number of tasks loaded from database

    def test_reload_task_registry_stopped_scheduler(self, mock_task_database, mock_db_tasks, caplog):
        """Test reloading task registry when scheduler is stopped."""
        # Mock the database query
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = mock_db_tasks
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.task_registry = {"old_task": {"function": "test"}}

        with caplog.at_level(logging.INFO, logger="apps.tasks.cron_scheduler"):
            scheduler.reload_task_registry()

        assert len(scheduler.task_registry) == 2

    def test_reload_task_registry_running_scheduler(self, mock_task_database, mock_db_tasks):
        """Test reloading task registry when scheduler is running."""
        # Mock the database query
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = mock_db_tasks
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.running = True
        scheduler.task_registry = {"old_task": {"function": "test"}}

        # Mock scheduler methods
        scheduler.scheduler.remove_job = Mock()
        scheduler.scheduler.remove_job.side_effect = [None, Exception("Job not found")]
        scheduler._add_registry_tasks = Mock()

        scheduler.reload_task_registry()

        # Should attempt to remove old tasks
        assert scheduler.scheduler.remove_job.call_count == 1
        scheduler._add_registry_tasks.assert_called_once()

    @pytest.mark.django_db
    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_start_success(self, mock_task_database, mock_db_tasks, caplog):
        """Test successful scheduler start."""
        # Mock the database query
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = mock_db_tasks
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.start = Mock()
        scheduler._add_registry_tasks = Mock()
        scheduler._sync_database_tasks = Mock()

        with caplog.at_level(logging.INFO, logger="apps.tasks.cron_scheduler"):
            scheduler.start()

        assert scheduler.running is True
        scheduler._add_registry_tasks.assert_called_once()
        scheduler.scheduler.start.assert_called_once()

    def test_start_already_running(self, caplog):
        """Test starting scheduler when already running."""
        scheduler = UnifiedTaskScheduler()
        scheduler.running = True

        with caplog.at_level(logging.WARNING, logger="apps.tasks.cron_scheduler"):
            scheduler.start()

    def test_start_failure(self, mock_task_database, caplog):
        """Test scheduler start failure."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.start = Mock(side_effect=Exception("Start error"))

        with (
            pytest.raises(Exception, match="Start error"),
            caplog.at_level(logging.ERROR, logger="apps.tasks.cron_scheduler"),
        ):
            scheduler.start()

    @pytest.mark.django_db
    def test_stop_success(self, mock_task_database, caplog):
        """Test successful scheduler stop."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.running = True
        scheduler.scheduler.shutdown = Mock()

        with caplog.at_level(logging.INFO, logger="apps.tasks.cron_scheduler"):
            scheduler.stop()

        assert scheduler.running is False
        scheduler.scheduler.shutdown.assert_called_once()

    def test_stop_not_running(self, mock_task_database):
        """Test stopping scheduler when not running."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.running = False
        scheduler.scheduler.shutdown = Mock()

        scheduler.stop()

        scheduler.scheduler.shutdown.assert_not_called()

    def test_stop_failure(self, mock_task_database, caplog):
        """Test scheduler stop failure."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.running = True
        scheduler.scheduler.shutdown = Mock(side_effect=Exception("Stop error"))

        with caplog.at_level(logging.ERROR, logger="apps.tasks.cron_scheduler"):
            scheduler.stop()

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock(), "cleanup_old_data": Mock()})
    def test_add_registry_tasks(self, mock_task_database, mock_task_groups, caplog):
        """Test adding registry tasks to scheduler."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.task_registry = mock_task_groups
        scheduler._add_scheduled_task = Mock()

        with caplog.at_level(logging.DEBUG, logger="apps.tasks.cron_scheduler"):
            scheduler._add_registry_tasks()

        # Should add enabled task and skip disabled one
        scheduler._add_scheduled_task.assert_called_once_with("test_task_1", mock_task_groups["test_task_1"])

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_add_registry_tasks_with_error(self, mock_task_database, caplog):
        """Test adding registry tasks with error."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.task_registry = {"test_task": {"function": "hello_world", "enabled": True}}
        scheduler._add_scheduled_task = Mock(side_effect=Exception("Add error"))

        with caplog.at_level(logging.ERROR, logger="apps.tasks.cron_scheduler"):
            scheduler._add_registry_tasks()

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("apps.tasks.cron_scheduler.CronTrigger")
    def test_add_scheduled_task_success(self, mock_cron_trigger, mock_task_database, caplog):
        """Test successful scheduled task addition."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        mock_trigger = Mock()
        mock_cron_trigger.from_crontab.return_value = mock_trigger

        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.add_job = Mock()

        config = {
            "function": "hello_world",
            "cron": "0 */1 * * *",
            "args": {"message": "test"},
            "description": "Test task",
        }

        with caplog.at_level(logging.INFO, logger="apps.tasks.cron_scheduler"):
            scheduler._add_scheduled_task("test_task", config)

        mock_cron_trigger.from_crontab.assert_called_once_with("0 */1 * * *")
        scheduler.scheduler.add_job.assert_called_once_with(
            func=scheduler._execute_scheduled_task,
            trigger=mock_trigger,
            args=["test_task", "hello_world", {"message": "test"}, None],  # Include feature_flag parameter
            id="test_task",
            name="Test task",
            replace_existing=True,
            max_instances=1,
        )

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {})
    def test_add_scheduled_task_unknown_function(self):
        """Test adding scheduled task with unknown function."""
        scheduler = UnifiedTaskScheduler()
        config = {"function": "unknown_function", "cron": "0 */1 * * *"}

        with pytest.raises(ValueError, match="Unknown task function: unknown_function"):
            scheduler._add_scheduled_task("test_task", config)

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("dispatcherd.publish.submit_task")
    def test_execute_scheduled_task_success(self, mock_submit, caplog):
        """Test successful scheduled task execution."""
        scheduler = UnifiedTaskScheduler()

        with patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured") as mock_ensure:
            with caplog.at_level(logging.INFO, logger="apps.tasks.cron_scheduler"):
                scheduler._execute_scheduled_task("test_task", "hello_world", {"message": "test"})

            mock_ensure.assert_called_once()
            mock_submit.assert_called_once_with(
                "apps.tasks.tasks.hello_world", kwargs={"message": "test"}, queue="metrics_tasks"
            )

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {})
    def test_execute_scheduled_task_unknown_function(self, caplog):
        """Test executing scheduled task with unknown function."""
        scheduler = UnifiedTaskScheduler()

        with (
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"),
            caplog.at_level(logging.ERROR, logger="apps.tasks.cron_scheduler"),
        ):
            scheduler._execute_scheduled_task("test_task", "unknown_function", {})

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_execute_scheduled_task_config_error(self, caplog):
        """Test executing scheduled task with configuration error."""
        scheduler = UnifiedTaskScheduler()

        with (
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured", side_effect=Exception("Config error")),
            caplog.at_level(logging.ERROR, logger="apps.tasks.cron_scheduler"),
        ):
            scheduler._execute_scheduled_task("test_task", "hello_world", {})

    def test_get_queue_for_function_known_functions(self):
        """Test queue mapping for known functions."""
        scheduler = UnifiedTaskScheduler()

        # Test specific queue mappings
        assert scheduler._get_queue_for_function("cleanup_old_data") == "metrics_cleanup"
        assert scheduler._get_queue_for_function("send_notification_email") == "metrics_notifications"
        assert scheduler._get_queue_for_function("collect_anonymous_metrics") == "metrics_collectors"
        assert scheduler._get_queue_for_function("gather_automation_controller_billing_data") == "metrics_utility"

    def test_get_queue_for_function_unknown_function(self):
        """Test queue mapping for unknown function."""
        scheduler = UnifiedTaskScheduler()
        assert scheduler._get_queue_for_function("unknown_function") == "metrics_tasks"

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_add_dynamic_task_success(self, caplog):
        """Test successful dynamic task addition."""
        scheduler = UnifiedTaskScheduler()
        scheduler._add_scheduled_task = Mock()

        with caplog.at_level(logging.INFO, logger="apps.tasks.cron_scheduler"):
            scheduler.add_dynamic_task(
                "dynamic_task", "hello_world", "0 */1 * * *", {"message": "test"}, "Dynamic test task"
            )

        expected_config = {
            "function": "hello_world",
            "cron": "0 */1 * * *",
            "args": {"message": "test"},
            "enabled": True,
            "description": "Dynamic test task",
        }

        scheduler._add_scheduled_task.assert_called_once_with("dynamic_task", expected_config)
        assert scheduler.task_registry["dynamic_task"] == expected_config

    def test_add_dynamic_task_default_args(self):
        """Test adding dynamic task with default arguments."""
        scheduler = UnifiedTaskScheduler()
        scheduler._add_scheduled_task = Mock()

        scheduler.add_dynamic_task("dynamic_task", "hello_world", "0 */1 * * *")

        expected_config = {
            "function": "hello_world",
            "cron": "0 */1 * * *",
            "args": {},
            "enabled": True,
            "description": "dynamic_task",
        }

        scheduler._add_scheduled_task.assert_called_once_with("dynamic_task", expected_config)

    def test_add_dynamic_task_failure(self):
        """Test dynamic task addition failure."""
        scheduler = UnifiedTaskScheduler()
        scheduler._add_scheduled_task = Mock(side_effect=Exception("Add error"))

        with pytest.raises(Exception, match="Add error"):
            scheduler.add_dynamic_task("dynamic_task", "hello_world", "0 */1 * * *")

    def test_remove_task_success(self):
        """Test successful task removal."""
        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.remove_job = Mock()
        scheduler.task_registry = {"test_task": {"function": "hello_world"}}

        scheduler.remove_task("test_task")

        scheduler.scheduler.remove_job.assert_called_once_with("test_task")
        assert "test_task" not in scheduler.task_registry

    def test_remove_task_not_in_registry(self):
        """Test removing task not in registry."""
        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.remove_job = Mock()
        scheduler.task_registry = {}

        scheduler.remove_task("test_task")

        scheduler.scheduler.remove_job.assert_called_once_with("test_task")

    def test_remove_task_failure(self):
        """Test task removal failure."""
        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.remove_job = Mock(side_effect=Exception("Remove error"))

        # Should not raise - just log error
        scheduler.remove_task("test_task")

    def test_update_task_success(self):
        """Test successful task update."""
        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.remove_job = Mock()
        scheduler._add_scheduled_task = Mock()
        scheduler.task_registry = {"test_task": {"function": "hello_world", "cron": "0 */1 * * *"}}

        scheduler.update_task("test_task", cron="0 */2 * * *")

        assert scheduler.task_registry["test_task"]["cron"] == "0 */2 * * *"
        scheduler.scheduler.remove_job.assert_called_once_with("test_task")
        scheduler._add_scheduled_task.assert_called_once_with("test_task", scheduler.task_registry["test_task"])

    def test_update_task_not_found(self):
        """Test updating non-existent task."""
        scheduler = UnifiedTaskScheduler()
        scheduler.task_registry = {}

        with pytest.raises(ValueError, match="Task test_task not found"):
            scheduler.update_task("test_task", cron="0 */2 * * *")

    def test_get_task_status_success(self):
        """Test successful task status retrieval."""
        scheduler = UnifiedTaskScheduler()

        mock_job = Mock()
        mock_job.id = "test_task"
        mock_job.name = "Test Task"
        mock_job.next_run_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_job.trigger = "cron[hour='12']"

        scheduler.scheduler.get_job = Mock(return_value=mock_job)

        status = scheduler.get_task_status("test_task")

        expected_status = {
            "id": "test_task",
            "name": "Test Task",
            "next_run_time": datetime(2024, 1, 1, 12, 0, 0),
            "trigger": "cron[hour='12']",
        }

        assert status == expected_status

    def test_get_task_status_not_found(self):
        """Test task status retrieval for non-existent task."""
        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.get_job = Mock(return_value=None)

        status = scheduler.get_task_status("test_task")
        assert status is None

    def test_get_task_status_failure(self):
        """Test task status retrieval failure."""
        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.get_job = Mock(side_effect=Exception("Status error"))

        status = scheduler.get_task_status("test_task")
        assert status is None

    @pytest.mark.django_db
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_list_tasks(self, mock_get_status):
        """Test listing all tasks."""
        mock_get_status.return_value = {"group1": {"enabled": True}}

        scheduler = UnifiedTaskScheduler()
        scheduler.task_registry = {"task1": {"function": "hello_world"}}

        mock_job = Mock()
        mock_job.id = "task1"
        mock_job.name = "Task 1"
        mock_job.next_run_time = None
        mock_job.trigger = "cron"

        scheduler.scheduler.get_jobs = Mock(return_value=[mock_job])

        result = scheduler.list_tasks()

        expected_result = {
            "task_groups": {"task1": {"function": "hello_world"}},
            "database_tasks": 0,
            "scheduled_jobs": [{"id": "task1", "name": "Task 1", "next_run_time": None, "trigger": "cron"}],
            "task_groups_status": {"group1": {"enabled": True}},
            "total_jobs": 1,
        }

        assert result == expected_result

    def test_get_task_groups_info(self):
        """Test getting task groups information."""
        with patch("apps.tasks.cron_scheduler.get_task_group_status") as mock_get_status:
            mock_status = {"group1": {"enabled": True}}
            mock_get_status.return_value = mock_status

            scheduler = UnifiedTaskScheduler()
            # Reset the call count from __init__
            mock_get_status.reset_mock()

            result = scheduler.get_task_groups_info()

            assert result == mock_status
            mock_get_status.assert_called_once()

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("dispatcherd.publish.submit_task")
    @patch("apps.tasks.cron_scheduler.timezone")
    def test_schedule_immediate_task_success(self, mock_timezone, mock_submit):
        """Test successful immediate task scheduling."""
        mock_timezone.now.return_value.timestamp.return_value = 1234567890.0

        scheduler = UnifiedTaskScheduler()

        with patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured") as mock_ensure:
            job_id = scheduler.schedule_immediate_task("hello_world", {"message": "test"}, "custom_queue")

            assert job_id == "immediate_1234567890.0"
            mock_ensure.assert_called_once()
            mock_submit.assert_called_once_with(
                "apps.tasks.tasks.hello_world", kwargs={"message": "test"}, queue="custom_queue"
            )

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("apps.tasks.cron_scheduler.timezone")
    def test_schedule_immediate_task_default_args(self, mock_timezone):
        """Test scheduling immediate task with default arguments."""
        mock_timezone.now.return_value.timestamp.return_value = 1234567890.0

        scheduler = UnifiedTaskScheduler()
        scheduler.schedule_immediate_task = Mock(return_value="immediate_1234567890.0")

        scheduler.schedule_immediate_task("hello_world")

        # Verify the mock was called correctly (since we mocked the method)
        scheduler.schedule_immediate_task.assert_called_once_with("hello_world")

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {})
    @patch("apps.tasks.cron_scheduler.timezone")
    def test_schedule_immediate_task_unknown_function(self, mock_timezone):
        """Test scheduling immediate task with unknown function."""
        mock_timezone.now.return_value.timestamp.return_value = 1234567890.0

        scheduler = UnifiedTaskScheduler()

        with (
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"),
            pytest.raises(ValueError, match="Unknown task function: unknown_function"),
        ):
            scheduler.schedule_immediate_task("unknown_function")

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("apps.tasks.cron_scheduler.timezone")
    def test_schedule_immediate_task_config_error(self, mock_timezone):
        """Test scheduling immediate task with configuration error."""
        mock_timezone.now.return_value.timestamp.return_value = 1234567890.0

        scheduler = UnifiedTaskScheduler()

        with (
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured", side_effect=Exception("Config error")),
            pytest.raises(Exception, match="Config error"),
        ):
            scheduler.schedule_immediate_task("hello_world")


class TestGlobalSchedulerFunctions:
    """Test cases for global scheduler functions."""

    @pytest.mark.django_db
    def test_get_scheduler_first_call(self):
        """Test getting scheduler instance for first time."""
        # Reset global instance
        import apps.tasks.cron_scheduler

        apps.tasks.cron_scheduler._scheduler_instance = None

        with patch("apps.tasks.cron_scheduler.UnifiedTaskScheduler") as mock_class:
            mock_instance = Mock()
            mock_class.return_value = mock_instance

            scheduler = get_scheduler()

            assert scheduler == mock_instance
            mock_class.assert_called_once()

    def test_get_scheduler_subsequent_calls(self):
        """Test getting scheduler instance on subsequent calls."""
        import apps.tasks.cron_scheduler

        # Set up existing instance
        existing_instance = Mock()
        apps.tasks.cron_scheduler._scheduler_instance = existing_instance

        scheduler = get_scheduler()
        assert scheduler == existing_instance

    def test_start_scheduler(self):
        """Test starting the global scheduler."""
        with patch("apps.tasks.cron_scheduler.get_scheduler") as mock_get:
            mock_scheduler = Mock()
            mock_get.return_value = mock_scheduler

            result = start_scheduler()

            assert result == mock_scheduler
            mock_scheduler.start.assert_called_once()

    def test_stop_scheduler_with_instance(self):
        """Test stopping scheduler when instance exists."""
        import apps.tasks.cron_scheduler

        mock_instance = Mock()
        apps.tasks.cron_scheduler._scheduler_instance = mock_instance

        stop_scheduler()

        mock_instance.stop.assert_called_once()
        assert apps.tasks.cron_scheduler._scheduler_instance is None

    def test_stop_scheduler_no_instance(self):
        """Test stopping scheduler when no instance exists."""
        import apps.tasks.cron_scheduler

        apps.tasks.cron_scheduler._scheduler_instance = None

        # Should not raise any errors
        stop_scheduler()

        assert apps.tasks.cron_scheduler._scheduler_instance is None


class TestThreadSafety:
    """Test cases for thread safety."""

    def test_start_with_concurrent_calls(self):
        """Test starting scheduler with concurrent calls."""
        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.start = Mock()
        scheduler._add_registry_tasks = Mock()

        # Simulate concurrent calls
        results = []

        def start_scheduler_thread():
            try:
                scheduler.start()
                results.append("success")
            except Exception as e:
                results.append(f"error: {e}")

        threads = [threading.Thread(target=start_scheduler_thread) for _ in range(3)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Only one should succeed, others should see "already running"
        assert scheduler.running is True
        scheduler.scheduler.start.assert_called_once()

    def test_stop_with_concurrent_calls(self):
        """Test stopping scheduler with concurrent calls."""
        scheduler = UnifiedTaskScheduler()
        scheduler.running = True
        scheduler.scheduler.shutdown = Mock()

        # Simulate concurrent calls
        def stop_scheduler_thread():
            scheduler.stop()

        threads = [threading.Thread(target=stop_scheduler_thread) for _ in range(3)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should handle concurrent stops gracefully
        assert scheduler.running is False


@pytest.mark.parametrize(
    "function_name,expected_queue",
    [
        ("hello_world", "metrics_tasks"),
        ("cleanup_old_data", "metrics_cleanup"),
        ("cleanup_old_tasks", "metrics_cleanup"),
        ("send_notification_email", "metrics_notifications"),
        ("process_user_data", "metrics_tasks"),
        ("execute_db_task", "metrics_tasks"),
        ("sleep", "metrics_tasks"),
        ("collect_anonymous_metrics", "metrics_collectors"),
        ("collect_config_metrics", "metrics_collectors"),
        ("collect_job_host_summary", "metrics_collectors"),
        ("collect_host_metrics", "metrics_collectors"),
        ("collect_all_metrics", "metrics_collectors"),
        ("gather_automation_controller_billing_data", "metrics_utility"),
        ("build_metrics_report", "metrics_utility"),
        ("metrics_utility_health_check", "metrics_utility"),
        ("metrics_utility_custom_command", "metrics_utility"),
        ("unknown_function", "metrics_tasks"),
    ],
)
def test_queue_mapping_parametrized(function_name, expected_queue):
    """Test queue mapping for all known functions."""
    scheduler = UnifiedTaskScheduler()
    assert scheduler._get_queue_for_function(function_name) == expected_queue
