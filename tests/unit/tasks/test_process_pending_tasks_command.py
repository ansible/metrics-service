"""
Unit tests for process_pending_tasks management command.
"""

from io import StringIO
from unittest.mock import Mock, patch

from django.core.management.base import BaseCommand
from django.db import DatabaseError
from django.test import TestCase

from apps.tasks.management.commands.process_pending_tasks import Command


class ProcessPendingTasksCommandTestCase(TestCase):
    """Test cases for process_pending_tasks management command."""

    def setUp(self):
        """Set up test data."""
        self.command = Command()

    def test_command_help_text(self):
        """Test command help text is set correctly."""
        self.assertEqual(
            self.command.help, "Process all pending tasks in the database by submitting them to dispatcherd"
        )

    @patch("apps.tasks.models.Task.objects.filter")
    def test_handle_no_pending_tasks(self, mock_filter):
        """Test handling when no pending tasks exist."""
        # Mock empty queryset
        mock_filter.return_value = []

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"

        self.command.handle(limit=50, dry_run=False)

        output = out.getvalue()
        self.assertIn("No pending tasks found", output)

    @patch("apps.tasks.models.Task.objects.filter")
    def test_handle_dry_run_mode(self, mock_filter):
        """Test dry run mode functionality."""
        # Create mock tasks
        mock_task1 = Mock()
        mock_task1.id = 1
        mock_task1.name = "Test Task 1"
        mock_task1.function_name = "test_function"
        mock_task1.is_ready_to_run.return_value = True

        mock_task2 = Mock()
        mock_task2.id = 2
        mock_task2.name = "Test Task 2"
        mock_task2.function_name = "test_function2"
        mock_task2.is_ready_to_run.return_value = False

        mock_filter.return_value = [mock_task1, mock_task2]

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.WARNING = lambda x: f"WARNING: {x}"

        self.command.handle(limit=50, dry_run=True)

        output = out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("Test Task 1", output)
        self.assertIn("Test Task 2", output)
        self.assertIn("✓ Ready", output)
        self.assertIn("⏳ Not ready", output)

    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    @patch("apps.tasks.models.Task.objects.filter")
    def test_handle_successful_processing(self, mock_filter, mock_submit):
        """Test successful task processing."""
        # Create mock task
        mock_task = Mock()
        mock_task.id = 1
        mock_task.name = "Test Task"
        mock_task.function_name = "test_function"
        mock_task.is_ready_to_run.return_value = True

        mock_filter.return_value = [mock_task]

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"
        self.command.style.ERROR = lambda x: f"ERROR: {x}"

        self.command.handle(limit=50, dry_run=False)

        output = out.getvalue()
        self.assertIn("✅ Submitted 1: Test Task", output)
        self.assertIn("✅ Processed: 1", output)
        self.assertIn("⏭️  Skipped: 0", output)
        self.assertIn("❌ Errors: 0", output)

        mock_submit.assert_called_once_with(mock_task)

    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    @patch("apps.tasks.models.Task.objects.filter")
    def test_handle_skipped_tasks(self, mock_filter, mock_submit):
        """Test skipping tasks that are not ready."""
        # Create mock task that's not ready
        mock_task = Mock()
        mock_task.id = 1
        mock_task.name = "Not Ready Task"
        mock_task.function_name = "test_function"
        mock_task.is_ready_to_run.return_value = False

        mock_filter.return_value = [mock_task]

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"

        self.command.handle(limit=50, dry_run=False)

        output = out.getvalue()
        self.assertIn("⏭️  Skipped 1: Not Ready Task", output)
        self.assertIn("✅ Processed: 0", output)
        self.assertIn("⏭️  Skipped: 1", output)

        mock_submit.assert_not_called()

    @patch("apps.tasks.tasks.submit_task_to_dispatcher")
    @patch("apps.tasks.models.Task.objects.filter")
    def test_handle_submission_error(self, mock_filter, mock_submit):
        """Test handling submission errors."""
        # Create mock task
        mock_task = Mock()
        mock_task.id = 1
        mock_task.name = "Error Task"
        mock_task.function_name = "test_function"
        mock_task.is_ready_to_run.return_value = True

        mock_filter.return_value = [mock_task]
        mock_submit.side_effect = Exception("Submission failed")

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"
        self.command.style.ERROR = lambda x: f"ERROR: {x}"

        self.command.handle(limit=50, dry_run=False)

        output = out.getvalue()
        self.assertIn("❌ Failed 1: Error Task", output)
        self.assertIn("✅ Processed: 0", output)
        self.assertIn("❌ Errors: 1", output)

    @patch("apps.tasks.models.Task.objects.filter")
    def test_handle_general_exception(self, mock_filter):
        """Test handling general exceptions."""
        mock_filter.side_effect = DatabaseError("Database error")

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.ERROR = lambda x: f"ERROR: {x}"

        with self.assertRaises(DatabaseError):
            self.command.handle(limit=50, dry_run=False)

        output = out.getvalue()
        self.assertIn("Failed to process pending tasks", output)

    def test_add_arguments(self):
        """Test command line argument configuration."""
        parser = Mock()
        self.command.add_arguments(parser)

        # Verify add_argument was called for both options
        self.assertEqual(parser.add_argument.call_count, 2)

        # Check limit argument
        parser.add_argument.assert_any_call(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of tasks to process (default: 50)",
        )

        # Check dry-run argument
        parser.add_argument.assert_any_call(
            "--dry-run",
            action="store_true",
            help="Show what would be processed without actually submitting tasks",
        )

    def test_command_inheritance(self):
        """Test command inherits from BaseCommand."""
        self.assertIsInstance(self.command, BaseCommand)
