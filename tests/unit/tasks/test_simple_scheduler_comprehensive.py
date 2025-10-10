"""
Comprehensive unit tests for simple scheduler.
"""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from apps.tasks.simple_scheduler import SimpleTaskScheduler


class SimpleTaskSchedulerTestCase(TestCase):
    """Test cases for SimpleTaskScheduler."""

    def setUp(self):
        """Set up test data."""
        self.scheduler = SimpleTaskScheduler()

    def tearDown(self):
        """Clean up after tests."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.stop()

    def test_init(self):
        """Test SimpleTaskScheduler initialization."""
        scheduler = SimpleTaskScheduler()

        self.assertFalse(scheduler.running)
        self.assertIsNone(scheduler.thread)
        self.assertEqual(scheduler.check_interval, 30)

    def test_start_scheduler(self):
        """Test starting the scheduler."""
        with patch("threading.Thread") as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance

            self.scheduler.start()

            self.assertTrue(self.scheduler.running)
            self.assertEqual(self.scheduler.thread, mock_thread_instance)
            mock_thread.assert_called_once_with(target=self.scheduler._run_loop, daemon=True)
            mock_thread_instance.start.assert_called_once()

    def test_start_scheduler_already_running(self):
        """Test starting scheduler when already running."""
        self.scheduler.running = True

        with patch("threading.Thread") as mock_thread:
            self.scheduler.start()

            mock_thread.assert_not_called()

    def test_stop_scheduler(self):
        """Test stopping the scheduler."""
        mock_thread = Mock()
        self.scheduler.thread = mock_thread
        self.scheduler.running = True

        self.scheduler.stop()

        self.assertFalse(self.scheduler.running)
        mock_thread.join.assert_called_once_with(timeout=5)

    def test_stop_scheduler_no_thread(self):
        """Test stopping scheduler when no thread exists."""
        self.scheduler.running = True
        self.scheduler.thread = None

        # Should not raise exception
        self.scheduler.stop()

        self.assertFalse(self.scheduler.running)

    @patch("time.sleep")
    @patch.object(SimpleTaskScheduler, "_process_pending_tasks")
    @patch.object(SimpleTaskScheduler, "_process_scheduled_tasks")
    def test_run_loop_single_iteration(self, mock_scheduled, mock_pending, mock_sleep):
        """Test single iteration of run loop."""
        # Set up to run only one iteration
        self.scheduler.running = True

        def stop_after_first_call(*args):
            self.scheduler.running = False

        mock_sleep.side_effect = stop_after_first_call

        self.scheduler._run_loop()

        mock_pending.assert_called_once()
        mock_scheduled.assert_called_once()
        mock_sleep.assert_called_once_with(30)

    @patch("time.sleep")
    @patch.object(SimpleTaskScheduler, "_process_pending_tasks")
    @patch.object(SimpleTaskScheduler, "_process_scheduled_tasks")
    def test_run_loop_exception_handling(self, mock_scheduled, mock_pending, mock_sleep):
        """Test run loop handles exceptions gracefully."""
        self.scheduler.running = True

        # Make first call raise exception, second call stops the loop
        mock_pending.side_effect = [Exception("Test error"), None]

        def stop_after_calls(*args):
            if mock_sleep.call_count >= 2:
                self.scheduler.running = False

        mock_sleep.side_effect = stop_after_calls

        # Should not raise exception
        self.scheduler._run_loop()

        self.assertEqual(mock_pending.call_count, 2)

    @patch("apps.tasks.models.Task.objects.filter")
    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    def test_process_pending_tasks_success(self, mock_submit, mock_filter):
        """Test processing pending tasks successfully."""
        # Create mock tasks
        mock_task1 = Mock()
        mock_task1.is_ready_to_run.return_value = True
        mock_task1.id = 1
        mock_task1.name = "Task 1"

        mock_task2 = Mock()
        mock_task2.is_ready_to_run.return_value = False
        mock_task2.id = 2
        mock_task2.name = "Task 2"

        mock_filter.return_value = [mock_task1, mock_task2]

        self.scheduler._process_pending_tasks()

        mock_submit.assert_called_once_with(mock_task1)
        mock_task1.is_ready_to_run.assert_called_once()
        mock_task2.is_ready_to_run.assert_called_once()

    @patch("apps.tasks.models.Task.objects.filter")
    def test_process_pending_tasks_no_tasks(self, mock_filter):
        """Test processing pending tasks with no tasks."""
        mock_filter.return_value = []

        # Should not raise exception
        self.scheduler._process_pending_tasks()

    @patch("apps.tasks.models.Task.objects.filter")
    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    def test_process_pending_tasks_submission_error(self, mock_submit, mock_filter):
        """Test processing pending tasks with submission error."""
        mock_task = Mock()
        mock_task.is_ready_to_run.return_value = True
        mock_task.id = 1
        mock_task.name = "Task 1"

        mock_filter.return_value = [mock_task]
        mock_submit.side_effect = Exception("Submission failed")

        # Should not raise exception
        self.scheduler._process_pending_tasks()

    @patch("apps.tasks.models.Task.objects.filter")
    def test_process_scheduled_tasks_no_tasks(self, mock_filter):
        """Test processing scheduled tasks with no tasks."""
        mock_filter.return_value = []

        # Should not raise exception
        self.scheduler._process_scheduled_tasks()

    @patch("apps.tasks.models.Task.objects.filter")
    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    @patch("django.utils.timezone.now")
    def test_process_scheduled_tasks_due_task(self, mock_now, mock_submit, mock_filter):
        """Test processing scheduled tasks with due task."""
        current_time = timezone.now()
        mock_now.return_value = current_time

        # Create mock task that's due
        mock_task = Mock()
        mock_task.scheduled_time = current_time - timedelta(minutes=1)
        mock_task.id = 1
        mock_task.name = "Scheduled Task"

        mock_filter.return_value = [mock_task]

        self.scheduler._process_scheduled_tasks()

        mock_submit.assert_called_once_with(mock_task)

    @patch("apps.tasks.models.Task.objects.filter")
    @patch("django.utils.timezone.now")
    def test_process_scheduled_tasks_not_due(self, mock_now, mock_filter):
        """Test processing scheduled tasks with task not due yet."""
        current_time = timezone.now()
        mock_now.return_value = current_time

        # Create mock task that's not due yet
        mock_task = Mock()
        mock_task.scheduled_time = current_time + timedelta(minutes=1)
        mock_task.id = 1
        mock_task.name = "Future Task"

        mock_filter.return_value = [mock_task]

        with patch("apps.tasks.tasks.submit_task_to_dispatcher") as mock_submit:
            self.scheduler._process_scheduled_tasks()

            mock_submit.assert_not_called()

    @patch("apps.tasks.models.Task.objects.filter")
    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    @patch("django.utils.timezone.now")
    def test_process_scheduled_tasks_submission_error(self, mock_now, mock_submit, mock_filter):
        """Test processing scheduled tasks with submission error."""
        current_time = timezone.now()
        mock_now.return_value = current_time

        mock_task = Mock()
        mock_task.scheduled_time = current_time - timedelta(minutes=1)
        mock_task.id = 1
        mock_task.name = "Error Task"

        mock_filter.return_value = [mock_task]
        mock_submit.side_effect = Exception("Submission failed")

        # Should not raise exception
        self.scheduler._process_scheduled_tasks()

    @patch("apps.tasks.models.Task.objects.filter")
    @patch.object(SimpleTaskScheduler, "_should_create_recurring_task")
    @patch.object(SimpleTaskScheduler, "_create_recurring_task")
    def test_process_recurring_tasks(self, mock_create, mock_should_create, mock_filter):
        """Test processing recurring tasks."""
        mock_task = Mock()
        mock_task.cron_expression = "0 0 * * *"
        mock_task.is_recurring = True
        mock_task.id = 1
        mock_task.name = "Recurring Task"

        mock_filter.return_value = [mock_task]
        mock_should_create.return_value = True

        self.scheduler._process_recurring_tasks()

        mock_should_create.assert_called_once_with(mock_task)
        mock_create.assert_called_once_with(mock_task)

    @patch("apps.tasks.models.Task.objects.filter")
    @patch.object(SimpleTaskScheduler, "_should_create_recurring_task")
    def test_process_recurring_tasks_should_not_create(self, mock_should_create, mock_filter):
        """Test processing recurring tasks when shouldn't create."""
        mock_task = Mock()
        mock_task.cron_expression = "0 0 * * *"
        mock_task.is_recurring = True

        mock_filter.return_value = [mock_task]
        mock_should_create.return_value = False

        with patch.object(self.scheduler, "_create_recurring_task") as mock_create:
            self.scheduler._process_recurring_tasks()

            mock_create.assert_not_called()

    @patch("croniter.croniter")
    def test_should_create_recurring_task_due(self, mock_croniter):
        """Test should create recurring task when due."""
        mock_task = Mock()
        mock_task.cron_expression = "0 0 * * *"
        mock_task.last_run = timezone.now() - timedelta(days=2)

        mock_cron_instance = Mock()
        mock_cron_instance.get_next.return_value = (timezone.now() - timedelta(hours=1)).timestamp()
        mock_croniter.return_value = mock_cron_instance

        result = self.scheduler._should_create_recurring_task(mock_task)

        self.assertTrue(result)

    @patch("croniter.croniter")
    def test_should_create_recurring_task_not_due(self, mock_croniter):
        """Test should create recurring task when not due."""
        mock_task = Mock()
        mock_task.cron_expression = "0 0 * * *"
        mock_task.last_run = timezone.now() - timedelta(hours=1)

        mock_cron_instance = Mock()
        mock_cron_instance.get_next.return_value = (timezone.now() + timedelta(hours=1)).timestamp()
        mock_croniter.return_value = mock_cron_instance

        result = self.scheduler._should_create_recurring_task(mock_task)

        self.assertFalse(result)

    def test_should_create_recurring_task_invalid_cron(self):
        """Test should create recurring task with invalid cron expression."""
        mock_task = Mock()
        mock_task.cron_expression = "invalid cron"

        with patch("croniter.croniter", side_effect=ValueError("Invalid cron")):
            result = self.scheduler._should_create_recurring_task(mock_task)

            self.assertFalse(result)

    @patch("apps.tasks.models.Task.objects.create")
    def test_create_recurring_task_success(self, mock_create):
        """Test creating recurring task successfully."""
        mock_task = Mock()
        mock_task.name = "Original Task"
        mock_task.function_name = "test_function"
        mock_task.task_data = {"param": "value"}
        mock_task.cron_expression = "0 0 * * *"
        mock_task.priority = 1
        mock_task.max_attempts = 3
        mock_task.timeout_seconds = 300
        mock_task.created_by = None

        mock_new_task = Mock()
        mock_create.return_value = mock_new_task

        self.scheduler._create_recurring_task(mock_task)

        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]

        self.assertIn("(recurring)", call_args["name"])
        self.assertEqual(call_args["function_name"], "test_function")
        self.assertEqual(call_args["task_data"], {"param": "value"})

    @patch("apps.tasks.models.Task.objects.create")
    def test_create_recurring_task_exception(self, mock_create):
        """Test creating recurring task with exception."""
        mock_task = Mock()
        mock_task.name = "Original Task"

        mock_create.side_effect = Exception("Creation failed")

        # Should not raise exception
        self.scheduler._create_recurring_task(mock_task)

    def test_is_running_true(self):
        """Test is_running when scheduler is running."""
        self.scheduler.running = True

        self.assertTrue(self.scheduler.is_running())

    def test_is_running_false(self):
        """Test is_running when scheduler is not running."""
        self.scheduler.running = False

        self.assertFalse(self.scheduler.is_running())

    def test_module_imports(self):
        """Test that all required imports work."""
        from apps.tasks import simple_scheduler

        # Test that key classes are available
        self.assertTrue(hasattr(simple_scheduler, "SimpleTaskScheduler"))

    def test_logger_configured(self):
        """Test that logger is properly configured."""
        from apps.tasks import simple_scheduler

        self.assertTrue(hasattr(simple_scheduler, "logger"))
        self.assertEqual(simple_scheduler.logger.name, "apps.tasks.simple_scheduler")
