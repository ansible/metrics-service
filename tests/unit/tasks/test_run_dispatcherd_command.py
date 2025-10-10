"""
Unit tests for run_dispatcherd management command.
"""

import logging
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management.base import BaseCommand
from django.test import TestCase

from apps.tasks.management.commands.run_dispatcherd import Command


class RunDispatcherdCommandTestCase(TestCase):
    """Test cases for run_dispatcherd management command."""

    def setUp(self):
        """Set up test data."""
        self.command = Command()

    def test_command_help_text(self):
        """Test command help text is set correctly."""
        self.assertEqual(self.command.help, "Run dispatcherd worker processes for background task processing")

    def test_add_arguments(self):
        """Test command line argument configuration."""
        parser = Mock()
        self.command.add_arguments(parser)

        # Verify add_argument was called for all options
        self.assertEqual(parser.add_argument.call_count, 4)

        # Check workers argument
        parser.add_argument.assert_any_call(
            "--workers",
            type=int,
            default=4,
            help="Number of worker processes (default: 4)",
        )

        # Check timeout argument
        parser.add_argument.assert_any_call(
            "--timeout",
            type=int,
            default=3600,
            help="Task timeout in seconds (default: 3600)",
        )

        # Check max-tasks argument
        parser.add_argument.assert_any_call(
            "--max-tasks",
            type=int,
            default=100,
            help="Maximum tasks per worker before respawn (default: 100)",
        )

        # Check log-level argument
        parser.add_argument.assert_any_call(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level (default: INFO)",
        )

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    @patch("logging.basicConfig")
    def test_handle_successful_start(self, mock_basic_config, mock_setup):
        """Test successful dispatcherd startup."""
        with patch.dict("sys.modules", {"dispatcherd": Mock()}):
            import dispatcherd

            dispatcherd.run_service = Mock()

            out = StringIO()
            self.command.stdout = out
            self.command.style = Mock()
            self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"

            options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

            self.command.handle(**options)

            # Verify configuration setup
            mock_setup.assert_called_once()
            mock_basic_config.assert_called_once_with(level=logging.INFO)

            # Verify dispatcherd was started
            dispatcherd.run_service.assert_called_once()

            # Verify output
            output = out.getvalue()
            self.assertIn("Starting dispatcherd with 4 workers", output)
            self.assertIn("timeout: 3600s", output)
            self.assertIn("max_tasks: 100", output)

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    @patch("logging.basicConfig")
    def test_handle_custom_options(self, mock_basic_config, mock_setup):
        """Test handling with custom options."""
        with patch.dict("sys.modules", {"dispatcherd": Mock()}):
            import dispatcherd

            dispatcherd.run_service = Mock()

            out = StringIO()
            self.command.stdout = out
            self.command.style = Mock()
            self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"

            options = {"workers": 8, "timeout": 1800, "max_tasks": 50, "log_level": "DEBUG"}

            self.command.handle(**options)

            # Verify DEBUG log level was set
            mock_basic_config.assert_called_once_with(level=logging.DEBUG)

            # Verify output reflects custom options
            output = out.getvalue()
            self.assertIn("Starting dispatcherd with 8 workers", output)
            self.assertIn("timeout: 1800s", output)
            self.assertIn("max_tasks: 50", output)

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    @patch("logging.basicConfig")
    @patch("sys.exit")
    def test_handle_import_error(self, mock_exit, mock_basic_config, mock_setup):
        """Test handling dispatcherd import errors."""
        # Simulate ImportError when importing dispatcherd
        with patch.dict("sys.modules", {}):
            out = StringIO()
            self.command.stdout = out
            self.command.style = Mock()
            self.command.style.ERROR = lambda x: f"ERROR: {x}"

            options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

            self.command.handle(**options)

            # Verify error handling
            output = out.getvalue()
            self.assertIn("Failed to import dispatcherd", output)
            mock_exit.assert_called_once_with(1)

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    @patch("logging.basicConfig")
    @patch("sys.exit")
    def test_handle_general_exception(self, mock_exit, mock_basic_config, mock_setup):
        """Test handling general exceptions."""
        mock_setup.side_effect = Exception("Configuration failed")

        out = StringIO()
        self.command.stdout = out
        self.command.style = Mock()
        self.command.style.ERROR = lambda x: f"ERROR: {x}"

        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        self.command.handle(**options)

        # Verify error handling
        output = out.getvalue()
        self.assertIn("Failed to start dispatcherd", output)
        self.assertIn("Configuration failed", output)
        mock_exit.assert_called_once_with(1)

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    @patch("logging.basicConfig")
    def test_log_level_conversion(self, mock_basic_config, mock_setup):
        """Test log level string to constant conversion."""
        with patch.dict("sys.modules", {"dispatcherd": Mock()}):
            import dispatcherd

            dispatcherd.run_service = Mock()

            out = StringIO()
            self.command.stdout = out
            self.command.style = Mock()
            self.command.style.SUCCESS = lambda x: f"SUCCESS: {x}"

            # Test different log levels
            test_cases = [
                ("DEBUG", logging.DEBUG),
                ("INFO", logging.INFO),
                ("WARNING", logging.WARNING),
                ("ERROR", logging.ERROR),
            ]

            for log_level_str, expected_level in test_cases:
                options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": log_level_str}

                self.command.handle(**options)

                # Find the call with the expected log level
                calls = mock_basic_config.call_args_list
                found_call = any(call[1].get("level") == expected_level for call in calls)
                self.assertTrue(found_call, f"Expected log level {expected_level} not found in calls")

    def test_command_inheritance(self):
        """Test command inherits from BaseCommand."""
        self.assertIsInstance(self.command, BaseCommand)
