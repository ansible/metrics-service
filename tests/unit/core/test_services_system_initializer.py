"""
Unit tests for SystemInitializer service.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError
from django.test import TestCase

from apps.core.services.output_formatter import OutputFormatter
from apps.core.services.system_initializer import SystemInitializer
from apps.tasks.models import Task


@pytest.mark.unit
class SystemInitializerTestCase(TestCase):
    """Test cases for SystemInitializer service."""

    def setUp(self):
        """Set up test fixtures."""
        self.stdout = StringIO()
        self.style = MagicMock()
        # Make style methods return the message string directly
        self.style.SUCCESS.side_effect = lambda msg: msg
        self.style.ERROR.side_effect = lambda msg: msg
        self.style.WARNING.side_effect = lambda msg: msg
        self.output_formatter = OutputFormatter(self.stdout, self.style)
        self.system_initializer = SystemInitializer(self.output_formatter)

    def test_initialization(self):
        """Test SystemInitializer initialization."""
        self.assertEqual(self.system_initializer.output, self.output_formatter)

    @patch("apps.core.services.system_initializer.ServiceID")
    def test_init_service_id_creates_new(self, mock_service_id):
        """Test ServiceID creation when none exists."""
        # Mock ServiceID.objects.count() to return 0
        mock_service_id.objects.count.return_value = 0

        # Mock ServiceID creation
        mock_service_instance = MagicMock()
        mock_service_instance.pk = "test-service-id-123"
        mock_service_id.objects.create.return_value = mock_service_instance

        self.system_initializer.init_service_id()

        mock_service_id.objects.count.assert_called_once()
        mock_service_id.objects.create.assert_called_once()
        self.style.SUCCESS.assert_called_once_with("Created ServiceID: test-service-id-123")

    @patch("apps.core.services.system_initializer.ServiceID")
    def test_init_service_id_exists(self, mock_service_id):
        """Test ServiceID handling when one already exists."""
        # Mock ServiceID.objects.count() to return 1
        mock_service_id.objects.count.return_value = 1

        # Mock existing ServiceID
        mock_existing = MagicMock()
        mock_existing.pk = "existing-service-id-456"
        mock_service_id.objects.first.return_value = mock_existing

        self.system_initializer.init_service_id()

        mock_service_id.objects.count.assert_called_once()
        mock_service_id.objects.create.assert_not_called()
        mock_service_id.objects.first.assert_called_once()
        self.style.WARNING.assert_called_once_with("ServiceID exists: existing-service-id-456")

    @patch("apps.core.services.system_initializer.ServiceID")
    def test_init_service_id_exception(self, mock_service_id):
        """Test ServiceID initialization with exception."""
        mock_service_id.objects.count.side_effect = Exception("Database error")

        with self.assertRaises(CommandError) as cm:
            self.system_initializer.init_service_id()

        self.assertIn("Failed to initialize ServiceID", str(cm.exception))
        self.assertIn("Database error", str(cm.exception))

    @patch("apps.tasks.tasks.create_system_tasks")
    def test_init_system_tasks_list_option(self, mock_create_tasks):
        """Test init_system_tasks with list option."""
        options = {"list": True}

        with patch.object(self.system_initializer, "_list_system_tasks") as mock_list:
            self.system_initializer.init_system_tasks(options)

            mock_list.assert_called_once()
            mock_create_tasks.assert_not_called()

    @patch("apps.tasks.tasks.create_system_tasks")
    def test_init_system_tasks_dry_run_option(self, mock_create_tasks):
        """Test init_system_tasks with dry_run option."""
        options = {"dry_run": True}

        with patch.object(self.system_initializer, "_handle_dry_run") as mock_dry_run:
            self.system_initializer.init_system_tasks(options)

            mock_dry_run.assert_called_once()
            mock_create_tasks.assert_not_called()

    @patch("apps.tasks.tasks.create_system_tasks")
    def test_init_system_tasks_execute(self, mock_create_tasks):
        """Test init_system_tasks execution."""
        options = {}

        with patch.object(self.system_initializer, "_execute_initialization") as mock_execute:
            self.system_initializer.init_system_tasks(options)

            mock_execute.assert_called_once_with(mock_create_tasks)

    def test_init_system_tasks_import_error(self):
        """Test init_system_tasks with import error."""
        options = {}

        with patch(
            "apps.tasks.tasks.create_system_tasks",
            side_effect=ImportError("Module not found"),
        ):
            with self.assertRaises(CommandError) as cm:
                self.system_initializer.init_system_tasks(options)

            self.assertIn("Failed to initialize system tasks", str(cm.exception))
            self.assertIn("Module not found", str(cm.exception))

    def test_handle_dry_run(self):
        """Test dry run handling."""
        with patch.object(self.system_initializer, "_list_system_tasks") as mock_list:
            self.system_initializer._handle_dry_run()

            mock_list.assert_called_once()

            # Check output
            output = self.stdout.getvalue()
            self.assertIn("DRY RUN", output)
            self.assertIn("no changes will be made", output)

    @patch("apps.core.services.system_initializer.time")
    def test_execute_initialization_success(self, mock_time):
        """Test successful initialization execution."""
        mock_time.time.side_effect = [100.0, 105.5]  # Start and end times

        mock_create_system_tasks = MagicMock()
        mock_results = {"created": 2, "updated": 1, "skipped": 3}
        mock_create_system_tasks.return_value = mock_results

        with patch.object(self.system_initializer, "_display_results") as mock_display:
            self.system_initializer._execute_initialization(mock_create_system_tasks)

            mock_create_system_tasks.assert_called_once()
            mock_display.assert_called_once_with(mock_results, 5.5)

            # Check that success message was output
            self.style.SUCCESS.assert_called()

    def test_execute_initialization_exception(self):
        """Test initialization execution with exception."""
        mock_create_system_tasks = MagicMock()
        mock_create_system_tasks.side_effect = Exception("Initialization failed")

        with self.assertRaises(CommandError) as cm:
            self.system_initializer._execute_initialization(mock_create_system_tasks)

        self.assertIn("Failed to initialize system tasks", str(cm.exception))
        self.assertIn("Initialization failed", str(cm.exception))

    def test_display_results_complete(self):
        """Test displaying complete results."""
        results = {
            "created": 2,
            "updated": 1,
            "skipped": 3,
            "tasks": ["Created: Task A", "Updated: Task B", "Skipped: Task C", "Error: Task D failed"],
        }
        elapsed_time = 4.5

        with patch.object(self.system_initializer, "_display_task_details") as mock_display_details:
            self.system_initializer._display_results(results, elapsed_time)

            mock_display_details.assert_called_once_with(results)

            # Check output
            output = self.stdout.getvalue()
            self.assertIn("Created: 2 tasks", output)
            self.assertIn("Updated: 1 tasks", output)
            self.assertIn("Skipped: 3 tasks", output)
            self.assertIn("Processed 6 system tasks in 4.50 seconds", output)

    def test_display_results_minimal(self):
        """Test displaying results with minimal data."""
        results = {"created": 0, "updated": 0, "skipped": 0}
        elapsed_time = 1.0

        self.system_initializer._display_results(results, elapsed_time)

        output = self.stdout.getvalue()
        self.assertIn("Processed 0 system tasks in 1.00 seconds", output)

    def test_display_task_details_complete(self):
        """Test displaying task details."""
        results = {
            "tasks": [
                "Created: New cleanup task",
                "Updated: Modified backup task",
                "Skipped: Unchanged monitoring task",
                "Error: Failed to create metrics task",
                "Other: Unknown operation",
            ]
        }

        self.system_initializer._display_task_details(results)

        output = self.stdout.getvalue()
        self.assertIn("Task Details:", output)
        self.assertIn("✅ Created: New cleanup task", output)
        self.assertIn("🔄 Updated: Modified backup task", output)
        self.assertIn("⏭️  Skipped: Unchanged monitoring task", output)
        self.assertIn("❌ Error: Failed to create metrics task", output)
        self.assertIn("ℹ️  Other: Unknown operation", output)

    def test_display_task_details_empty(self):
        """Test displaying task details with no tasks."""
        results = {}

        self.system_initializer._display_task_details(results)

        # Should not output anything
        output = self.stdout.getvalue()
        self.assertEqual(output.strip(), "")

    def test_list_system_tasks_with_tasks(self):
        """Test listing system tasks when tasks exist."""
        # Create mock tasks
        mock_task1 = MagicMock()
        mock_task1.function_name = "cleanup_old_data"
        mock_task1.name = "Cleanup Task"
        mock_task1.status = "pending"
        mock_task1.is_recurring = True
        mock_task1.cron_expression = "0 2 * * *"
        mock_task1.priority = 2

        mock_task2 = MagicMock()
        mock_task2.function_name = "collect_metrics"
        mock_task2.name = "Metrics Task"
        mock_task2.status = "completed"
        mock_task2.is_recurring = False
        mock_task2.cron_expression = None
        mock_task2.priority = 3

        mock_queryset = MagicMock()
        mock_queryset.exists.return_value = True
        mock_queryset.__iter__ = lambda self: iter([mock_task1, mock_task2])

        with patch.object(Task.objects, "filter") as mock_filter:
            mock_filter.return_value.order_by.return_value = mock_queryset

            with (
                patch.object(self.system_initializer, "_categorize_tasks") as mock_categorize,
                patch.object(self.system_initializer, "_display_task_info") as mock_display_info,
            ):
                mock_categorize.return_value = {"MAINTENANCE": [mock_task1], "METRICS": [mock_task2]}

                self.system_initializer._list_system_tasks()

                mock_filter.assert_called_once_with(is_system_task=True)
                mock_categorize.assert_called_once()

                # Should display info for each task
                self.assertEqual(mock_display_info.call_count, 2)

                # Check output
                output = self.stdout.getvalue()
                self.assertIn("Current System Tasks", output)
                self.assertIn("MAINTENANCE (1 tasks)", output)
                self.assertIn("METRICS (1 tasks)", output)
                self.assertIn("Total: 2 system tasks", output)

    def test_list_system_tasks_empty(self):
        """Test listing system tasks when none exist."""
        mock_queryset = MagicMock()
        mock_queryset.exists.return_value = False

        with patch.object(Task.objects, "filter") as mock_filter:
            mock_filter.return_value.order_by.return_value = mock_queryset

            self.system_initializer._list_system_tasks()

            output = self.stdout.getvalue()
            self.assertIn("No system tasks found", output)

    def test_list_system_tasks_exception(self):
        """Test listing system tasks with exception."""
        with patch.object(Task.objects, "filter", side_effect=Exception("Database error")):
            self.system_initializer._list_system_tasks()

            # Should catch exception and display error
            self.style.ERROR.assert_called()
            error_call = self.style.ERROR.call_args[0][0]
            self.assertIn("Failed to list system tasks", error_call)
            self.assertIn("Database error", error_call)

    def test_categorize_tasks(self):
        """Test task categorization."""
        mock_task1 = MagicMock()
        mock_task1.function_name = "cleanup_old_data"

        mock_task2 = MagicMock()
        mock_task2.function_name = "collect_system_metrics"

        mock_task3 = MagicMock()
        mock_task3.function_name = "unknown_function"

        tasks = [mock_task1, mock_task2, mock_task3]

        result = self.system_initializer._categorize_tasks(tasks)

        expected = {"MAINTENANCE": [mock_task1], "METRICS": [mock_task2], "OTHER": [mock_task3]}

        self.assertEqual(result, expected)

    def test_display_task_info(self):
        """Test displaying individual task info."""
        mock_task = MagicMock()
        mock_task.name = "Test Task"
        mock_task.function_name = "test_function"
        mock_task.status = "pending"
        mock_task.is_recurring = True
        mock_task.cron_expression = "0 2 * * *"
        mock_task.priority = 3

        self.system_initializer._display_task_info(mock_task)

        output = self.stdout.getvalue()
        self.assertIn("⏳ 🔄 Test Task", output)  # pending + recurring icons
        self.assertIn("Function: test_function", output)
        self.assertIn("Schedule: 0 2 * * *", output)
        self.assertIn("Priority: 3 | Status: pending", output)

    def test_display_task_info_without_cron(self):
        """Test displaying task info without cron expression."""
        mock_task = MagicMock()
        mock_task.name = "One-time Task"
        mock_task.function_name = "onetime_function"
        mock_task.status = "completed"
        mock_task.is_recurring = False
        mock_task.cron_expression = None
        mock_task.priority = 1

        self.system_initializer._display_task_info(mock_task)

        output = self.stdout.getvalue()
        self.assertIn("✅ ➡️ One-time Task", output)  # completed + non-recurring icons
        self.assertIn("Function: onetime_function", output)
        self.assertNotIn("Schedule:", output)  # Should not show schedule
        self.assertIn("Priority: 1 | Status: completed", output)

    def test_edge_case_unicode_in_results(self):
        """Test handling unicode characters in results."""
        results = {
            "created": 1,
            "updated": 0,
            "skipped": 0,
            "tasks": ["Created: Unicode task 测试 🎉", "Error: Failed task with émojis 🚫"],
        }
        elapsed_time = 2.0

        # Should not raise any exceptions
        self.system_initializer._display_results(results, elapsed_time)

        output = self.stdout.getvalue()
        self.assertIn("测试 🎉", output)
        self.assertIn("émojis 🚫", output)

    def test_edge_case_large_numbers(self):
        """Test handling large numbers in results."""
        results = {"created": 1000, "updated": 500, "skipped": 2000}
        elapsed_time = 120.5

        self.system_initializer._display_results(results, elapsed_time)

        output = self.stdout.getvalue()
        self.assertIn("Created: 1000 tasks", output)
        self.assertIn("Updated: 500 tasks", output)
        self.assertIn("Skipped: 2000 tasks", output)
        self.assertIn("Processed 3500 system tasks in 120.50 seconds", output)
