"""
Comprehensive unit tests for the UnifiedTaskScheduler module.

Tests the task scheduler that combines task group scheduling and database task scheduling
without database polling, using APScheduler for optimal performance.
"""

from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.tasks.cron_scheduler import (
    UnifiedTaskScheduler,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
)

User = get_user_model()


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
            "function": "cleanup_old_tasks",
            "cron": "0 2 * * *",
            "args": {},
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
    task1.status = "pending"

    task2 = Mock()
    task2.id = 2
    task2.name = "test_task_2"
    task2.function_name = "cleanup_old_tasks"
    task2.cron_expression = "0 2 * * *"
    task2.task_data = {}
    task2.description = "Test task 2"
    task2.status = "pending"

    return [task1, task2]


@pytest.fixture
def mock_task():
    """Create a mock task object for one-time scheduled tasks."""
    task = Mock()
    task.id = 1
    task.name = "Test Task"
    task.status = "pending"
    task.function_name = "test_function"
    task.task_data = {}
    task.scheduled_time = timezone.now() + timedelta(hours=1)
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
    task.cron_expression = "0 * * * *"  # Every hour
    task.created = timezone.now()
    task.modified = timezone.now()
    task.save = Mock()
    return task


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
def mock_task_functions():
    """Mock task functions."""
    return {
        "hello_world": Mock(),
        "cleanup_old_tasks": Mock(),
        "execute_db_task": Mock(),
    }


@pytest.fixture
def scheduler():
    """Create a UnifiedTaskScheduler instance."""
    with patch("apps.tasks.models.Task") as mock_task_model:
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_model.objects.filter.return_value = mock_queryset
        return UnifiedTaskScheduler()


@pytest.mark.unit
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
        # Should have loaded tasks from database
        assert len(scheduler.task_registry) == 2
        assert "test_task_1" in scheduler.task_registry
        assert "test_task_2" in scheduler.task_registry

    def test_init_with_load_error(self, mock_task_database):
        """Test initialization handles load errors gracefully."""
        # Make database query fail
        mock_task_database.objects.filter.side_effect = Exception("Database error")

        scheduler = UnifiedTaskScheduler()

        assert scheduler.task_registry == {}

    def test_load_task_registry_success(self, mock_task_database, mock_db_tasks):
        """Test successful task registry loading."""
        # Mock the database query
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = mock_db_tasks
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()

        scheduler._load_task_registry()

        # Verify tasks were loaded
        assert len(scheduler.task_registry) == 2

    @pytest.mark.django_db
    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_start_success(self, mock_task_database, mock_db_tasks):
        """Test successful scheduler start."""
        # Mock the database query
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = mock_db_tasks
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.start = Mock()
        scheduler._add_registry_tasks = Mock()
        scheduler._sync_database_tasks = Mock()

        scheduler.start()

        assert scheduler.running is True
        scheduler._add_registry_tasks.assert_called_once()
        scheduler.scheduler.start.assert_called_once()

    def test_start_already_running(self):
        """Test starting scheduler when already running."""
        scheduler = UnifiedTaskScheduler()
        scheduler.running = True

        scheduler.start()  # Should just return without error

    def test_start_failure(self, mock_task_database):
        """Test scheduler start failure."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.scheduler.start = Mock(side_effect=Exception("Start error"))

        with pytest.raises(Exception, match="Start error"):
            scheduler.start()

    @pytest.mark.django_db
    def test_stop_success(self, mock_task_database):
        """Test successful scheduler stop."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.running = True
        scheduler._db_task_jobs[1] = "job_1"
        scheduler.scheduler.shutdown = Mock()

        scheduler.stop()

        assert scheduler.running is False
        assert len(scheduler._db_task_jobs) == 0
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

    def test_stop_failure(self, mock_task_database):
        """Test scheduler stop failure."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.running = True
        scheduler.scheduler.shutdown = Mock(side_effect=Exception("Stop error"))

        scheduler.stop()  # Should catch exception

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock(), "cleanup_old_tasks": Mock()})
    def test_add_registry_tasks(self, mock_task_database, mock_task_groups):
        """Test adding registry tasks to scheduler."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.task_registry = mock_task_groups
        scheduler._add_scheduled_task = Mock()

        scheduler._add_registry_tasks()

        # Should add enabled task and skip disabled one
        scheduler._add_scheduled_task.assert_called_once_with("test_task_1", mock_task_groups["test_task_1"])

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_add_registry_tasks_with_error(self, mock_task_database):
        """Test adding registry tasks with error."""
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_database.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        scheduler.task_registry = {"test_task": {"function": "hello_world", "enabled": True}}
        scheduler._add_scheduled_task = Mock(side_effect=Exception("Add error"))

        scheduler._add_registry_tasks()  # Should catch exception

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("apps.tasks.cron_scheduler.CronTrigger")
    def test_add_scheduled_task_success(self, mock_cron_trigger, mock_task_database):
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

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {})
    def test_add_scheduled_task_unknown_function(self):
        """Test adding scheduled task with unknown function."""
        scheduler = UnifiedTaskScheduler()
        config = {"function": "unknown_function", "cron": "0 */1 * * *"}

        with pytest.raises(ValueError, match="Unknown task function: unknown_function"):
            scheduler._add_scheduled_task("test_task", config)

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    @patch("dispatcherd.publish.submit_task")
    def test_execute_scheduled_task_success(self, mock_submit):
        """Test successful scheduled task execution."""
        scheduler = UnifiedTaskScheduler()

        with patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured") as mock_ensure:
            scheduler._execute_scheduled_task("test_task", "hello_world", {"message": "test"})

            mock_ensure.assert_called_once()
            mock_submit.assert_called_once_with(
                "apps.tasks.tasks.hello_world", kwargs={"message": "test"}, queue="metrics_tasks"
            )

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {})
    def test_execute_scheduled_task_unknown_function(self):
        """Test executing scheduled task with unknown function."""
        scheduler = UnifiedTaskScheduler()

        with patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"):
            scheduler._execute_scheduled_task("test_task", "unknown_function", {})  # Should log error

    @patch("apps.tasks.cron_scheduler.TASK_FUNCTIONS", {"hello_world": Mock()})
    def test_execute_scheduled_task_config_error(self):
        """Test executing scheduled task with configuration error."""
        scheduler = UnifiedTaskScheduler()

        with patch(
            "apps.tasks.dispatcherd_config.ensure_dispatcherd_configured", side_effect=Exception("Config error")
        ):
            scheduler._execute_scheduled_task("test_task", "hello_world", {})  # Should catch error

    def test_get_queue_for_function_known_functions(self):
        """Test queue mapping for known functions (now using shared function from dispatcherd_config)."""
        from apps.tasks.dispatcherd_config import get_queue_for_function

        # Test specific queue mappings
        assert get_queue_for_function("cleanup_old_tasks") == "metrics_cleanup"
        assert get_queue_for_function("daily_metrics_rollup") == "metrics_collectors"

    def test_get_queue_for_function_unknown_function(self):
        """Test queue mapping for unknown function (now using shared function from dispatcherd_config)."""
        from apps.tasks.dispatcherd_config import get_queue_for_function

        assert get_queue_for_function("unknown_function") == "metrics_tasks"


@pytest.mark.unit
class TestDatabaseTaskManagement:
    """Test cases for managing database tasks."""

    def test_add_database_scheduled_task(self, scheduler, mock_task):
        """Test adding a scheduled database task."""
        with patch.object(scheduler.scheduler, "add_job") as mock_add_job:
            scheduler._add_database_scheduled_task(mock_task)

            mock_add_job.assert_called_once()
            assert mock_task.id in scheduler._db_task_jobs

    def test_add_database_recurring_task(self, scheduler, mock_recurring_task):
        """Test adding a recurring database task."""
        with patch.object(scheduler.scheduler, "add_job") as mock_add_job:
            scheduler._add_database_recurring_task(mock_recurring_task)

            mock_add_job.assert_called_once()
            assert mock_recurring_task.id in scheduler._db_task_jobs

    def test_add_database_recurring_task_error(self, scheduler, mock_recurring_task):
        """Test error handling when adding recurring task fails."""
        with patch.object(scheduler.scheduler, "add_job", side_effect=Exception("Scheduler error")):
            # Should not raise - error is caught and logged
            scheduler._add_database_recurring_task(mock_recurring_task)
            # Task should not be in the jobs dict since adding failed
            assert mock_recurring_task.id not in scheduler._db_task_jobs

    def test_remove_database_task(self, scheduler):
        """Test removing a database task."""
        task_id = 1
        job_id = f"db_task_{task_id}"
        scheduler._db_task_jobs[task_id] = job_id

        with patch.object(scheduler.scheduler, "remove_job") as mock_remove:
            scheduler._remove_database_task(task_id)

            mock_remove.assert_called_once_with(job_id)
            assert task_id not in scheduler._db_task_jobs

    @patch("apps.tasks.models.Task")
    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_execute_database_task(self, mock_submit, mock_task_model, scheduler):
        """Test executing a database task."""
        task_id = 1
        mock_task = Mock()
        mock_task.id = task_id
        mock_task.name = "Test"
        mock_task.cron_expression = None  # Non-recurring task
        mock_task.status = "pending"

        mock_task_model.objects.get.return_value = mock_task

        with patch.object(scheduler, "_remove_database_task") as mock_remove:
            scheduler._execute_database_task(task_id)

            mock_submit.assert_called_once_with(mock_task)
            mock_remove.assert_called_once_with(task_id)

    @patch("apps.tasks.models.Task")
    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_execute_database_task_recurring(self, mock_submit, mock_task_model, scheduler):
        """Test executing a recurring database task."""
        task_id = 2
        mock_task = Mock()
        mock_task.id = task_id
        mock_task.name = "Recurring Test"
        mock_task.is_recurring = True
        mock_task.status = "pending"
        mock_task.function_name = "test_function"
        mock_task.task_data = {}
        mock_task.max_attempts = 3
        mock_task.timeout_seconds = 300
        mock_task.created_by = None
        mock_task.is_system_task = False

        # Mock the execution task that gets created
        mock_execution_task = Mock()
        mock_execution_task.id = 999
        mock_execution_task.name = "Recurring Test (Execution 2024-01-01 12:00:00)"

        mock_task_model.objects.get.return_value = mock_task
        mock_task_model.objects.create.return_value = mock_execution_task

        with patch.object(scheduler, "_remove_database_task") as mock_remove:
            scheduler._execute_database_task(task_id)

            # Should create execution task and submit that
            mock_task_model.objects.create.assert_called_once()
            mock_submit.assert_called_once_with(mock_execution_task)
            # Should not remove recurring tasks
            mock_remove.assert_not_called()

    @patch("apps.tasks.models.Task")
    def test_execute_database_task_not_found(self, mock_task_model, scheduler):
        """Test executing a task that doesn't exist."""
        from django.core.exceptions import ObjectDoesNotExist

        mock_task_model.objects.get.side_effect = ObjectDoesNotExist()
        mock_task_model.DoesNotExist = ObjectDoesNotExist

        with patch.object(scheduler, "_remove_database_task") as mock_remove:
            # Should not raise - error is caught and logged
            scheduler._execute_database_task(999)
            # Should remove the task from scheduler
            mock_remove.assert_called_once_with(999)


@pytest.mark.unit
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


@pytest.mark.parametrize(
    "function_name,expected_queue",
    [
        # System/general tasks
        ("hello_world", "metrics_tasks"),
        ("execute_db_task", "metrics_tasks"),
        # Cleanup tasks
        ("cleanup_old_tasks", "metrics_cleanup"),
        ("cleanup_metrics_data", "metrics_cleanup"),
        # Collection tasks
        ("collect_hourly_metrics", "metrics_collectors"),
        ("collect_snapshot_metrics", "metrics_collectors"),
        # Daily rollup and anonymization tasks
        ("daily_metrics_rollup", "metrics_collectors"),
        ("daily_anonymize_and_prepare", "metrics_collectors"),
        ("send_anonymized_to_segment", "metrics_collectors"),
        # Unknown function (default)
        ("unknown_function", "metrics_tasks"),
    ],
)
def test_queue_mapping_parametrized(function_name, expected_queue):
    """Test queue mapping for all known functions (now using shared function from dispatcherd_config)."""
    from apps.tasks.dispatcherd_config import get_queue_for_function

    assert get_queue_for_function(function_name) == expected_queue
