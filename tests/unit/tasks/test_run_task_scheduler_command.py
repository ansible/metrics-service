"""
Unit tests for run_task_scheduler management command.
"""

import logging
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management.base import BaseCommand
from django.test import TestCase

from apps.tasks.management.commands.run_task_scheduler import Command


class RunTaskSchedulerCommandTestCase(TestCase):
    """Test cases for run_task_scheduler management command."""

    def setUp(self):
        """Set up test data."""
        self.command = Command()

    def test_command_help_text(self):
        """Test command help text is set correctly."""
        self.assertEqual(self.command.help, "Run the task scheduler for cron-based recurring tasks")

    def test_add_arguments(self):
        """Test command line argument configuration."""
        parser = Mock()
        self.command.add_arguments(parser)

        # Verify add_argument was called for both options
        self.assertEqual(parser.add_argument.call_count, 2)

        # Check log-level argument
        parser.add_argument.assert_any_call(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level (default: INFO)",
        )

        # Check check-interval argument
        parser.add_argument.assert_any_call(
            "--check-interval",
            type=int,
            default=60,
            help="Check interval in seconds (default: 60)",
        )

    @patch("time.sleep")
    @patch("apps.tasks.cron_scheduler.get_scheduler")
    @patch("apps.tasks.cron_scheduler.start_scheduler")
    @patch("logging.basicConfig")
    def test_handle_successful_start(self, mock_basic_config, mock_start, mock_get, mock_sleep):
        """Test successful scheduler startup."""
        # Mock scheduler
        mock_scheduler = Mock()
        mock_scheduler.running = True
        mock_get.return_value = mock_scheduler

        # Make sleep raise KeyboardInterrupt to exit the loop
        mock_sleep.side_effect = KeyboardInterrupt()

        with patch("apps.tasks.cron_scheduler.stop_scheduler") as mock_stop:
            out = StringIO()
            self.command.stdout = out
            self.command.style = Mock()
            self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"
            self.command.style.WARNING = lambda x: f"WARNING: {x}"

            options = {"log_level": "INFO", "check_interval": 60}

            self.command.handle(**options)

            # Verify configuration setup
            mock_basic_config.assert_called_once_with(level=logging.INFO)
            mock_start.assert_called_once()
            mock_get.assert_called_once()
            mock_stop.assert_called_once()

            # Verify output
            output = out.getvalue()
            self.assertIn("Starting task scheduler (check interval: 60s)", output)
            self.assertIn("Task scheduler started successfully", output)
            self.assertIn("Received interrupt signal", output)
            self.assertIn("Task scheduler stopped", output)

    @patch("time.sleep")
    @patch("apps.tasks.cron_scheduler.get_scheduler")
    @patch("apps.tasks.cron_scheduler.start_scheduler")
    @patch("logging.basicConfig")
    def test_handle_scheduler_stops_unexpectedly(self, mock_basic_config, mock_start, mock_get, mock_sleep):
        """Test handling when scheduler stops unexpectedly."""
        # Mock scheduler that stops
        mock_scheduler = Mock()
        mock_scheduler.running = False
        mock_get.return_value = mock_scheduler

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"
        self.command.style.ERROR = lambda x: f"ERROR: {x}"

        options = {"log_level": "INFO", "check_interval": 60}

        self.command.handle(**options)

        # Verify error message
        output = out.getvalue()
        self.assertIn("Scheduler stopped unexpectedly", output)

    @patch("logging.basicConfig")
    @patch("sys.exit")
    def test_handle_import_error(self, mock_exit, mock_basic_config):
        """Test handling import errors."""
        # Simulate ImportError
        with patch("apps.tasks.cron_scheduler.start_scheduler", side_effect=ImportError("Module not found")):
            out = StringIO()
            self.command.stdout = out
            self.command.style = Mock()
            self.command.style.ERROR = lambda x: f"ERROR: {x}"

            options = {"log_level": "INFO", "check_interval": 60}

            self.command.handle(**options)

            # Verify error handling
            output = out.getvalue()
            self.assertIn("Failed to import scheduler", output)
            mock_exit.assert_called_once_with(1)

    @patch("logging.basicConfig")
    @patch("sys.exit")
    def test_handle_general_exception(self, mock_exit, mock_basic_config):
        """Test handling general exceptions."""
        mock_basic_config.side_effect = Exception("Configuration failed")

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.ERROR = lambda x: f"ERROR: {x}"

        options = {"log_level": "INFO", "check_interval": 60}

        self.command.handle(**options)

        # Verify error handling
        output = out.getvalue()
        self.assertIn("Failed to start task scheduler", output)
        mock_exit.assert_called_once_with(1)

    @patch("time.sleep")
    @patch("apps.tasks.cron_scheduler.get_scheduler")
    @patch("apps.tasks.cron_scheduler.start_scheduler")
    @patch("logging.basicConfig")
    def test_custom_check_interval(self, mock_basic_config, mock_start, mock_get, mock_sleep):
        """Test custom check interval."""
        # Mock scheduler
        mock_scheduler = Mock()
        mock_scheduler.running = True
        mock_get.return_value = mock_scheduler

        # Make sleep raise KeyboardInterrupt to exit the loop
        mock_sleep.side_effect = KeyboardInterrupt()

        with patch("apps.tasks.cron_scheduler.stop_scheduler"):
            out = StringIO()
            self.command.stdout = out
            self.command.style = Mock()
            self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"
            self.command.style.WARNING = lambda x: f"WARNING: {x}"

            options = {"log_level": "DEBUG", "check_interval": 30}

            self.command.handle(**options)

            # Verify custom interval in output
            output = out.getvalue()
            self.assertIn("check interval: 30s", output)

            # Verify sleep was called with custom interval
            mock_sleep.assert_called_with(30)

            # Verify DEBUG log level
            mock_basic_config.assert_called_once_with(level=logging.DEBUG)

    @patch("logging.basicConfig")
    def test_log_level_conversion(self, mock_basic_config):
        """Test log level string to constant conversion."""
        with (
            patch("apps.tasks.cron_scheduler.start_scheduler"),
            patch("apps.tasks.cron_scheduler.get_scheduler") as mock_get,
            patch("time.sleep", side_effect=KeyboardInterrupt()),
            patch("apps.tasks.cron_scheduler.stop_scheduler"),
        ):
            mock_scheduler = Mock()
            mock_scheduler.running = True
            mock_get.return_value = mock_scheduler

            out = StringIO()
            self.command.stdout = out
            self.command.style = Mock()
            self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"
            self.command.style.WARNING = lambda x: f"WARNING: {x}"

            # Test different log levels
            test_cases = [
                ("DEBUG", logging.DEBUG),
                ("INFO", logging.INFO),
                ("WARNING", logging.WARNING),
                ("ERROR", logging.ERROR),
            ]

            for log_level_str, expected_level in test_cases:
                options = {"log_level": log_level_str, "check_interval": 60}

                self.command.handle(**options)

                # Find the call with the expected log level
                calls = mock_basic_config.call_args_list
                found_call = any(call[1].get("level") == expected_level for call in calls)
                self.assertTrue(found_call, f"Expected log level {expected_level} not found in calls")

    def test_command_inheritance(self):
        """Test command inherits from BaseCommand."""
        self.assertIsInstance(self.command, BaseCommand)
