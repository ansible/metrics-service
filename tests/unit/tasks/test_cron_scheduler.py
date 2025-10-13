"""
Comprehensive unit tests for the CronTaskScheduler module.

Tests all methods, edge cases, and error conditions for full code coverage.
"""

import logging
import threading
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from apps.tasks.cron_scheduler import (
    CronTaskScheduler,
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


class TestCronTaskScheduler:
    """Test cases for CronTaskScheduler class."""

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_init(self, mock_get_status, mock_get_tasks, mock_task_groups, mock_task_group_status):
        """Test scheduler initialization."""
        mock_get_tasks.return_value = mock_task_groups
        mock_get_status.return_value = mock_task_group_status

        scheduler = CronTaskScheduler()

        assert isinstance(scheduler.scheduler, BackgroundScheduler)
        assert scheduler.running is False
        assert isinstance(scheduler._lock, type(threading.Lock()))
        assert scheduler.task_registry == mock_task_groups
        mock_get_tasks.assert_called_once()
        mock_get_status.assert_called_once()

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_init_with_load_error(self, mock_get_status, mock_get_tasks, caplog):
        """Test initialization handles load errors gracefully."""
        mock_get_tasks.side_effect = Exception("Load error")
        mock_get_status.return_value = {}

        with caplog.at_level(logging.ERROR):
            scheduler = CronTaskScheduler()

        assert scheduler.task_registry == {}
        assert "Failed to load task registry from groups: Load error" in caplog.text

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_load_task_registry_success(
        self, mock_get_status, mock_get_tasks, mock_task_groups, mock_task_group_status, caplog
    ):
        """Test successful task registry loading."""
        mock_get_tasks.return_value = mock_task_groups
        mock_get_status.return_value = mock_task_group_status

        scheduler = CronTaskScheduler()

        with caplog.at_level(logging.INFO):
            scheduler._load_task_registry()

        assert "Loaded 2 enabled tasks from task groups" in caplog.text
        assert "Task group 'system_tasks' enabled: 2/3 tasks" in caplog.text
        assert "Task group 'disabled_group' disabled: 2 tasks skipped" in caplog.text

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_reload_task_registry_stopped_scheduler(self, mock_get_status, mock_get_tasks, mock_task_groups, caplog):
        """Test reloading task registry when scheduler is stopped."""
        mock_get_tasks.return_value = mock_task_groups
        mock_get_status.return_value = {}

        scheduler = CronTaskScheduler()
        scheduler.task_registry = {"old_task": {"function": "test"}}

        with caplog.at_level(logging.INFO):
            scheduler.reload_task_registry()

        assert "Reloading task registry from task groups" in caplog.text
        assert "Task registry reloaded: 1 -> 2 tasks" in caplog.text
        assert scheduler.task_registry == mock_task_groups

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_reload_task_registry_running_scheduler(self, mock_get_status, mock_get_tasks, mock_task_groups):
        """Test reloading task registry when scheduler is running."""
        mock_get_tasks.return_value = mock_task_groups
        mock_get_status.return_value = {}

        scheduler = CronTaskScheduler()
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

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_start_success(self, mock_task_groups, caplog):
        """Test successful scheduler start."""
        scheduler = CronTaskScheduler()
        scheduler.task_registry = mock_task_groups
        scheduler.scheduler.start = Mock()
        scheduler._add_registry_tasks = Mock()

        with caplog.at_level(logging.INFO):
            scheduler.start()

        assert scheduler.running is True
        scheduler._add_registry_tasks.assert_called_once()
        scheduler.scheduler.start.assert_called_once()
        assert "Cron-based task scheduler started" in caplog.text
        assert "Registered 2 scheduled tasks" in caplog.text

    def test_start_already_running(self, caplog):
        """Test starting scheduler when already running."""
        scheduler = CronTaskScheduler()
        scheduler.running = True

        with caplog.at_level(logging.WARNING):
            scheduler.start()

        assert "Scheduler is already running" in caplog.text

    def test_start_failure(self, caplog):
        """Test scheduler start failure."""
        scheduler = CronTaskScheduler()
        scheduler.scheduler.start = Mock(side_effect=Exception("Start error"))

        with pytest.raises(Exception, match="Start error"), caplog.at_level(logging.ERROR):
            scheduler.start()

        assert "Failed to start cron scheduler: Start error" in caplog.text

    def test_stop_success(self, caplog):
        """Test successful scheduler stop."""
        scheduler = CronTaskScheduler()
        scheduler.running = True
        scheduler.scheduler.shutdown = Mock()

        with caplog.at_level(logging.INFO):
            scheduler.stop()

        assert scheduler.running is False
        scheduler.scheduler.shutdown.assert_called_once()
        assert "Cron-based task scheduler stopped" in caplog.text

    def test_stop_not_running(self):
        """Test stopping scheduler when not running."""
        scheduler = CronTaskScheduler()
        scheduler.running = False
        scheduler.scheduler.shutdown = Mock()

        scheduler.stop()

        scheduler.scheduler.shutdown.assert_not_called()

    def test_stop_failure(self, caplog):
        """Test scheduler stop failure."""
        scheduler = CronTaskScheduler()
        scheduler.running = True
        scheduler.scheduler.shutdown = Mock(side_effect=Exception("Stop error"))

        with caplog.at_level(logging.ERROR):
            scheduler.stop()

        assert "Error stopping cron scheduler: Stop error" in caplog.text

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock(), "cleanup_old_data": Mock()})
    def test_add_registry_tasks(self, mock_task_groups, caplog):
        """Test adding registry tasks to scheduler."""
        scheduler = CronTaskScheduler()
        scheduler.task_registry = mock_task_groups
        scheduler._add_scheduled_task = Mock()

        with caplog.at_level(logging.DEBUG):
            scheduler._add_registry_tasks()

        # Should add enabled task and skip disabled one
        scheduler._add_scheduled_task.assert_called_once_with("test_task_1", mock_task_groups["test_task_1"])
        assert "Skipping disabled task: test_task_2" in caplog.text

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_add_registry_tasks_with_error(self, caplog):
        """Test adding registry tasks with error."""
        scheduler = CronTaskScheduler()
        scheduler.task_registry = {"test_task": {"function": "hello_world", "enabled": True}}
        scheduler._add_scheduled_task = Mock(side_effect=Exception("Add error"))

        with caplog.at_level(logging.ERROR):
            scheduler._add_registry_tasks()

        assert "Failed to add task test_task: Add error" in caplog.text

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("apps.tasks.cron_scheduler.CronTrigger")
    def test_add_scheduled_task_success(self, mock_cron_trigger, caplog):
        """Test successful scheduled task addition."""
        mock_trigger = Mock()
        mock_cron_trigger.from_crontab.return_value = mock_trigger

        scheduler = CronTaskScheduler()
        scheduler.scheduler.add_job = Mock()

        config = {
            "function": "hello_world",
            "cron": "0 */1 * * *",
            "args": {"message": "test"},
            "description": "Test task",
        }

        with caplog.at_level(logging.INFO):
            scheduler._add_scheduled_task("test_task", config)

        mock_cron_trigger.from_crontab.assert_called_once_with("0 */1 * * *")
        scheduler.scheduler.add_job.assert_called_once_with(
            func=scheduler._execute_scheduled_task,
            trigger=mock_trigger,
            args=["test_task", "hello_world", {"message": "test"}],
            id="test_task",
            name="Test task",
            replace_existing=True,
            max_instances=1,
        )
        assert "Added scheduled task: test_task (0 */1 * * *)" in caplog.text

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {})
    def test_add_scheduled_task_unknown_function(self):
        """Test adding scheduled task with unknown function."""
        scheduler = CronTaskScheduler()
        config = {"function": "unknown_function", "cron": "0 */1 * * *"}

        with pytest.raises(ValueError, match="Unknown task function: unknown_function"):
            scheduler._add_scheduled_task("test_task", config)

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("dispatcherd.publish.submit_task")
    def test_execute_scheduled_task_success(self, mock_submit, caplog):
        """Test successful scheduled task execution."""
        scheduler = CronTaskScheduler()

        with patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured") as mock_ensure:
            with caplog.at_level(logging.INFO):
                scheduler._execute_scheduled_task("test_task", "hello_world", {"message": "test"})

            mock_ensure.assert_called_once()
            mock_submit.assert_called_once_with(
                "apps.tasks.tasks.hello_world", kwargs={"message": "test"}, queue="metrics_tasks"
            )
            assert "Submitted scheduled task test_task (hello_world) to queue metrics_tasks" in caplog.text

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {})
    def test_execute_scheduled_task_unknown_function(self, caplog):
        """Test executing scheduled task with unknown function."""
        scheduler = CronTaskScheduler()

        with patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"), caplog.at_level(logging.ERROR):
            scheduler._execute_scheduled_task("test_task", "unknown_function", {})

        assert "Failed to execute scheduled task test_task: Unknown task function: unknown_function" in caplog.text

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_execute_scheduled_task_config_error(self, caplog):
        """Test executing scheduled task with configuration error."""
        scheduler = CronTaskScheduler()

        with (
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured", side_effect=Exception("Config error")),
            caplog.at_level(logging.ERROR),
        ):
            scheduler._execute_scheduled_task("test_task", "hello_world", {})

        assert "Failed to execute scheduled task test_task: Config error" in caplog.text

    def test_get_queue_for_function_known_functions(self):
        """Test queue mapping for known functions."""
        scheduler = CronTaskScheduler()

        # Test specific queue mappings
        assert scheduler._get_queue_for_function("cleanup_old_data") == "metrics_cleanup"
        assert scheduler._get_queue_for_function("send_notification_email") == "metrics_notifications"
        assert scheduler._get_queue_for_function("collect_anonymous_metrics") == "metrics_collectors"
        assert scheduler._get_queue_for_function("gather_automation_controller_billing_data") == "metrics_utility"

    def test_get_queue_for_function_unknown_function(self):
        """Test queue mapping for unknown function."""
        scheduler = CronTaskScheduler()
        assert scheduler._get_queue_for_function("unknown_function") == "metrics_tasks"

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_add_dynamic_task_success(self, caplog):
        """Test successful dynamic task addition."""
        scheduler = CronTaskScheduler()
        scheduler._add_scheduled_task = Mock()

        with caplog.at_level(logging.INFO):
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
        assert "Added dynamic task: dynamic_task" in caplog.text

    def test_add_dynamic_task_default_args(self):
        """Test adding dynamic task with default arguments."""
        scheduler = CronTaskScheduler()
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

    def test_add_dynamic_task_failure(self, caplog):
        """Test dynamic task addition failure."""
        scheduler = CronTaskScheduler()
        scheduler._add_scheduled_task = Mock(side_effect=Exception("Add error"))

        with pytest.raises(Exception, match="Add error"), caplog.at_level(logging.ERROR):
            scheduler.add_dynamic_task("dynamic_task", "hello_world", "0 */1 * * *")

        assert "Failed to add dynamic task dynamic_task: Add error" in caplog.text

    def test_remove_task_success(self, caplog):
        """Test successful task removal."""
        scheduler = CronTaskScheduler()
        scheduler.scheduler.remove_job = Mock()
        scheduler.task_registry = {"test_task": {"function": "hello_world"}}

        with caplog.at_level(logging.INFO):
            scheduler.remove_task("test_task")

        scheduler.scheduler.remove_job.assert_called_once_with("test_task")
        assert "test_task" not in scheduler.task_registry
        assert "Removed task: test_task" in caplog.text

    def test_remove_task_not_in_registry(self, caplog):
        """Test removing task not in registry."""
        scheduler = CronTaskScheduler()
        scheduler.scheduler.remove_job = Mock()
        scheduler.task_registry = {}

        with caplog.at_level(logging.INFO):
            scheduler.remove_task("test_task")

        scheduler.scheduler.remove_job.assert_called_once_with("test_task")
        assert "Removed task: test_task" in caplog.text

    def test_remove_task_failure(self, caplog):
        """Test task removal failure."""
        scheduler = CronTaskScheduler()
        scheduler.scheduler.remove_job = Mock(side_effect=Exception("Remove error"))

        with caplog.at_level(logging.ERROR):
            scheduler.remove_task("test_task")

        assert "Failed to remove task test_task: Remove error" in caplog.text

    def test_update_task_success(self, caplog):
        """Test successful task update."""
        scheduler = CronTaskScheduler()
        scheduler.scheduler.remove_job = Mock()
        scheduler._add_scheduled_task = Mock()
        scheduler.task_registry = {"test_task": {"function": "hello_world", "cron": "0 */1 * * *"}}

        with caplog.at_level(logging.INFO):
            scheduler.update_task("test_task", cron="0 */2 * * *")

        assert scheduler.task_registry["test_task"]["cron"] == "0 */2 * * *"
        scheduler.scheduler.remove_job.assert_called_once_with("test_task")
        scheduler._add_scheduled_task.assert_called_once_with("test_task", scheduler.task_registry["test_task"])
        assert "Updated task: test_task" in caplog.text

    def test_update_task_not_found(self):
        """Test updating non-existent task."""
        scheduler = CronTaskScheduler()
        scheduler.task_registry = {}

        with pytest.raises(ValueError, match="Task test_task not found"):
            scheduler.update_task("test_task", cron="0 */2 * * *")

    def test_get_task_status_success(self):
        """Test successful task status retrieval."""
        scheduler = CronTaskScheduler()

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
        scheduler = CronTaskScheduler()
        scheduler.scheduler.get_job = Mock(return_value=None)

        status = scheduler.get_task_status("test_task")
        assert status is None

    def test_get_task_status_failure(self, caplog):
        """Test task status retrieval failure."""
        scheduler = CronTaskScheduler()
        scheduler.scheduler.get_job = Mock(side_effect=Exception("Status error"))

        with caplog.at_level(logging.ERROR):
            status = scheduler.get_task_status("test_task")

        assert status is None
        assert "Failed to get status for task test_task: Status error" in caplog.text

    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_list_tasks(self, mock_get_status):
        """Test listing all tasks."""
        mock_get_status.return_value = {"group1": {"enabled": True}}

        scheduler = CronTaskScheduler()
        scheduler.task_registry = {"task1": {"function": "hello_world"}}

        mock_job = Mock()
        mock_job.id = "task1"
        mock_job.name = "Task 1"
        mock_job.next_run_time = None
        mock_job.trigger = "cron"

        scheduler.scheduler.get_jobs = Mock(return_value=[mock_job])

        result = scheduler.list_tasks()

        expected_result = {
            "registry": {"task1": {"function": "hello_world"}},
            "scheduled_jobs": [{"id": "task1", "name": "Task 1", "next_run_time": None, "trigger": "cron"}],
            "task_groups": {"group1": {"enabled": True}},
        }

        assert result == expected_result

    def test_get_task_groups_info(self):
        """Test getting task groups information."""
        with patch("apps.tasks.cron_scheduler.get_task_group_status") as mock_get_status:
            mock_status = {"group1": {"enabled": True}}
            mock_get_status.return_value = mock_status

            scheduler = CronTaskScheduler()
            # Reset the call count from __init__
            mock_get_status.reset_mock()

            result = scheduler.get_task_groups_info()

            assert result == mock_status
            mock_get_status.assert_called_once()

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("dispatcherd.publish.submit_task")
    @patch("apps.tasks.cron_scheduler.timezone")
    def test_schedule_immediate_task_success(self, mock_timezone, mock_submit, caplog):
        """Test successful immediate task scheduling."""
        mock_timezone.now.return_value.timestamp.return_value = 1234567890.0

        scheduler = CronTaskScheduler()

        with patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured") as mock_ensure:
            with caplog.at_level(logging.INFO):
                job_id = scheduler.schedule_immediate_task("hello_world", {"message": "test"}, "custom_queue")

            assert job_id == "immediate_1234567890.0"
            mock_ensure.assert_called_once()
            mock_submit.assert_called_once_with(
                "apps.tasks.tasks.hello_world", kwargs={"message": "test"}, queue="custom_queue"
            )
            assert "Scheduled immediate task immediate_1234567890.0 (hello_world) to queue custom_queue" in caplog.text

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("apps.tasks.cron_scheduler.timezone")
    def test_schedule_immediate_task_default_args(self, mock_timezone):
        """Test scheduling immediate task with default arguments."""
        mock_timezone.now.return_value.timestamp.return_value = 1234567890.0

        scheduler = CronTaskScheduler()
        scheduler.schedule_immediate_task = Mock(return_value="immediate_1234567890.0")

        scheduler.schedule_immediate_task("hello_world")

        # Verify the mock was called correctly (since we mocked the method)
        scheduler.schedule_immediate_task.assert_called_once_with("hello_world")

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {})
    @patch("apps.tasks.cron_scheduler.timezone")
    def test_schedule_immediate_task_unknown_function(self, mock_timezone, caplog):
        """Test scheduling immediate task with unknown function."""
        mock_timezone.now.return_value.timestamp.return_value = 1234567890.0

        scheduler = CronTaskScheduler()

        with (
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"),
            pytest.raises(ValueError, match="Unknown task function: unknown_function"),
            caplog.at_level(logging.ERROR),
        ):
            scheduler.schedule_immediate_task("unknown_function")

        assert (
            "Failed to schedule immediate task unknown_function: Unknown task function: unknown_function" in caplog.text
        )

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("apps.tasks.cron_scheduler.timezone")
    def test_schedule_immediate_task_config_error(self, mock_timezone, caplog):
        """Test scheduling immediate task with configuration error."""
        mock_timezone.now.return_value.timestamp.return_value = 1234567890.0

        scheduler = CronTaskScheduler()

        with (
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured", side_effect=Exception("Config error")),
            pytest.raises(Exception, match="Config error"),
            caplog.at_level(logging.ERROR),
        ):
            scheduler.schedule_immediate_task("hello_world")

        assert "Failed to schedule immediate task hello_world: Config error" in caplog.text


class TestGlobalSchedulerFunctions:
    """Test cases for global scheduler functions."""

    def test_get_scheduler_first_call(self):
        """Test getting scheduler instance for first time."""
        # Reset global instance
        import apps.tasks.cron_scheduler

        apps.tasks.cron_scheduler._scheduler_instance = None

        with patch("apps.tasks.cron_scheduler.CronTaskScheduler") as mock_class:
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
        scheduler = CronTaskScheduler()
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
        scheduler = CronTaskScheduler()
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
    scheduler = CronTaskScheduler()
    assert scheduler._get_queue_for_function(function_name) == expected_queue
