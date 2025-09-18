"""
Comprehensive tests for apps/tasks/management/commands/run_dispatcherd.py

This test file provides complete coverage of the run_dispatcherd management command,
including argument parsing, configuration setup, import error handling, and execution flow.
"""

import contextlib
import logging
from io import StringIO
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.tasks.management.commands.run_dispatcherd import Command


@pytest.mark.unit
class TestRunDispatcherdCommand(TestCase):
    """Test cases for run_dispatcherd management command."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.stdout = StringIO()
        self.stderr = StringIO()
        self.command.stdout = self.stdout
        self.command.stderr = self.stderr

    def tearDown(self):
        """Clean up test fixtures."""
        # Ensure file handles are properly closed
        if hasattr(self, "stdout") and not self.stdout.closed:
            self.stdout.close()
        if hasattr(self, "stderr") and not self.stderr.closed:
            self.stderr.close()

    def test_command_help_text(self):
        """Test command help text is set correctly."""
        self.assertEqual(self.command.help, "Run dispatcherd background task worker")

    def test_add_arguments(self):
        """Test add_arguments method adds correct arguments."""
        parser = Mock()
        parser.add_argument = Mock()

        self.command.add_arguments(parser)

        # Verify all expected arguments were added
        expected_calls = [
            (("--workers",), {"type": int, "default": 4, "help": "Number of worker processes to spawn"}),
            (("--timeout",), {"type": int, "default": 3600, "help": "Task timeout in seconds"}),
            (("--max-tasks",), {"type": int, "default": 100, "help": "Maximum tasks per worker before respawn"}),
            (
                ("--log-level",),
                {
                    "choices": ["DEBUG", "INFO", "WARNING", "ERROR"],
                    "default": "INFO",
                    "help": "Log level for dispatcher",
                },
            ),
        ]

        self.assertEqual(parser.add_argument.call_count, 4)
        for i, (args, kwargs) in enumerate(expected_calls):
            call_args, call_kwargs = parser.add_argument.call_args_list[i]
            self.assertEqual(call_args, args)
            self.assertEqual(call_kwargs, kwargs)

    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_handle_import_error(self, mock_logger):
        """Test handle method with ImportError for dispatcherd."""
        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        # Mock the import to raise ImportError
        with patch("builtins.__import__", side_effect=ImportError("No module named 'dispatcherd'")):
            self.command.handle(**options)

        # Verify error logging and output
        mock_logger.error.assert_called_with("Failed to import dispatcherd: No module named 'dispatcherd'")
        output = self.stdout.getvalue()
        self.assertIn("Import failed: No module named 'dispatcherd'", output)

    @patch("dispatcherd.run_service")
    @patch("dispatcherd.config.setup")
    @patch("threading.Thread")
    @patch("apps.tasks.tasks.TaskScheduler")
    @patch("apps.tasks.tasks.TASK_FUNCTIONS", {"test_task": Mock()})
    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_handle_success_path(
        self, mock_logger, mock_task_scheduler, mock_thread, mock_dispatcherd_setup, mock_run_service
    ):
        """Test successful execution path of handle method."""
        options = {"workers": 2, "timeout": 1800, "max_tasks": 50, "log_level": "DEBUG"}

        # Mock database settings
        with override_settings(
            DATABASES={
                "default": {
                    "NAME": "test_db",
                    "USER": "test_user",
                    "PASSWORD": "test_pass",
                    "HOST": "localhost",
                    "PORT": "5432",
                }
            }
        ):
            # Mock scheduler instance
            mock_scheduler_instance = Mock()
            mock_task_scheduler.return_value = mock_scheduler_instance

            # Mock thread instance
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance

            self.command.handle(**options)

        # Verify initial success message
        output = self.stdout.getvalue()
        self.assertIn("Starting dispatcherd with 2 workers...", output)

        # Verify logging configuration
        expected_log_calls = [
            "Dispatcherd started with configuration:",
            "  Workers: 2",
            "  Timeout: 1800s",
            "  Max tasks per worker: 50",
            "  Log level: DEBUG",
            "  Available tasks: ['test_task']",
            "Configuring dispatcherd with database: localhost:5432/test_db",
        ]

        for expected_call in expected_log_calls:
            mock_logger.info.assert_any_call(expected_call)

        # Verify TaskScheduler was created and started
        mock_task_scheduler.assert_called_once_with(poll_interval=5)
        mock_thread.assert_called_once_with(target=mock_scheduler_instance.start, daemon=True)
        mock_thread_instance.start.assert_called_once()

        # Verify dispatcherd configuration
        expected_config = {
            "version": 2,
            "brokers": {
                "pg_notify": {
                    "config": {
                        "dbname": "test_db",
                        "user": "test_user",
                        "password": "test_pass",
                        "host": "localhost",
                        "port": "5432",
                    },
                    "channels": [
                        "metrics_tasks",
                        "metrics_cleanup",
                        "metrics_notifications",
                    ],
                },
            },
            "service": {
                "pool_kwargs": {"max_workers": 2},
            },
        }
        mock_dispatcherd_setup.assert_called_once_with(expected_config)

        # Verify success messages
        self.assertIn("Task scheduler started in background", output)
        self.assertIn("Starting dispatcherd service...", output)

        # Verify run_service was called
        mock_run_service.assert_called_once()

    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_handle_general_exception(self, mock_logger):
        """Test handle method with general exception."""
        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        # Mock to raise a general exception during import
        with patch("builtins.__import__", side_effect=Exception("Unexpected error")):
            self.command.handle(**options)

        # Verify error logging and output
        mock_logger.error.assert_called_with("Failed to start dispatcherd: Unexpected error")
        output = self.stdout.getvalue()
        self.assertIn("Start failed: Unexpected error", output)

    @patch("logging.getLogger")
    @patch("dispatcherd.run_service")
    @patch("dispatcherd.config.setup")
    @patch("threading.Thread")
    @patch("apps.tasks.tasks.TaskScheduler")
    @patch("apps.tasks.tasks.TASK_FUNCTIONS", {"test_task": Mock()})
    def test_logging_configuration(
        self, mock_task_scheduler, mock_thread, mock_dispatcherd_setup, mock_run_service, mock_get_logger
    ):
        """Test that logging is configured correctly."""
        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "WARNING"}

        # Mock the dispatcherd logger
        mock_dispatcherd_logger = Mock()
        mock_get_logger.return_value = mock_dispatcherd_logger

        with override_settings(
            DATABASES={
                "default": {
                    "NAME": "test_db",
                    "USER": "test_user",
                    "PASSWORD": "test_pass",
                    "HOST": "localhost",
                    "PORT": "5432",
                }
            }
        ):
            self.command.handle(**options)

        # Verify dispatcherd logger was configured
        mock_get_logger.assert_any_call("dispatcherd")
        mock_dispatcherd_logger.setLevel.assert_called_with(logging.WARNING)

    @patch("apps.tasks.tasks.TASK_FUNCTIONS", {})
    @patch("dispatcherd.run_service")
    @patch("dispatcherd.config.setup")
    @patch("threading.Thread")
    @patch("apps.tasks.tasks.TaskScheduler")
    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_empty_task_functions(
        self, mock_logger, mock_task_scheduler, mock_thread, mock_dispatcherd_setup, mock_run_service
    ):
        """Test behavior when TASK_FUNCTIONS is empty."""
        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        with override_settings(
            DATABASES={
                "default": {
                    "NAME": "test_db",
                    "USER": "test_user",
                    "PASSWORD": "test_pass",
                    "HOST": "localhost",
                    "PORT": "5432",
                }
            }
        ):
            self.command.handle(**options)

        # Verify empty task list is logged
        mock_logger.info.assert_any_call("  Available tasks: []")

    def test_database_config_extraction(self):
        """Test database configuration extraction from Django settings."""
        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        with (
            override_settings(
                DATABASES={
                    "default": {
                        "NAME": "custom_db",
                        "USER": "custom_user",
                        "PASSWORD": "custom_pass",
                        "HOST": "custom_host",
                        "PORT": "5433",
                    }
                }
            ),
            patch("dispatcherd.config.setup") as mock_setup,
            patch("dispatcherd.run_service"),
            patch("threading.Thread"),
            patch("apps.tasks.tasks.TaskScheduler"),
            patch("apps.tasks.tasks.TASK_FUNCTIONS", {}),
        ):
            self.command.handle(**options)

            # Verify database config was extracted correctly
            call_args = mock_setup.call_args[0][0]
            pg_config = call_args["brokers"]["pg_notify"]["config"]

            self.assertEqual(pg_config["dbname"], "custom_db")
            self.assertEqual(pg_config["user"], "custom_user")
            self.assertEqual(pg_config["password"], "custom_pass")
            self.assertEqual(pg_config["host"], "custom_host")
            self.assertEqual(pg_config["port"], "5433")

    # @patch("dispatcherd.run_service", side_effect=KeyboardInterrupt("User interrupted"))
    # @patch("dispatcherd.config.setup")
    # @patch("threading.Thread")
    # @patch("apps.tasks.tasks.TaskScheduler")
    # @patch("apps.tasks.tasks.TASK_FUNCTIONS", {})
    # @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    # def test_keyboard_interrupt_handling(
    #     self, mock_logger, mock_task_scheduler, mock_thread, mock_dispatcherd_setup, mock_run_service
    # ):
    #     """Test handling of KeyboardInterrupt during service run."""
    #     options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

    #     with override_settings(
    #         DATABASES={
    #             "default": {
    #                 "NAME": "test_db",
    #                 "USER": "test_user",
    #                 "PASSWORD": "test_pass",
    #                 "HOST": "localhost",
    #                 "PORT": "5432",
    #             }
    #         }
    #     ):
    #         self.command.handle(**options)

    #     # Verify exception was logged
    #     mock_logger.error.assert_called_with("Failed to start dispatcherd: User interrupted")

    #     # Verify error message was displayed
    #     output = self.stdout.getvalue()
    #     self.assertIn("Start failed: User interrupted", output)


@pytest.mark.unit
class TestRunDispatcherdCommandArguments(TestCase):
    """Test command line argument parsing and validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.stdout = StringIO()

    def tearDown(self):
        """Clean up test fixtures."""
        # Ensure file handles are properly closed
        if hasattr(self, "stdout") and not self.stdout.closed:
            self.stdout.close()

    def test_default_arguments(self):
        """Test command runs with default arguments."""
        with (
            patch("dispatcherd.run_service"),
            patch("dispatcherd.config.setup"),
            patch("threading.Thread"),
            patch("apps.tasks.tasks.TaskScheduler"),
            patch("apps.tasks.tasks.TASK_FUNCTIONS", {}),
            contextlib.suppress(Exception),
        ):
            call_command("run_dispatcherd", stdout=self.stdout)

        output = self.stdout.getvalue()
        self.assertIn("Starting dispatcherd with 4 workers", output)  # Default workers

    def test_custom_arguments(self):
        """Test command with custom arguments."""
        with (
            patch("dispatcherd.run_service"),
            patch("dispatcherd.config.setup"),
            patch("threading.Thread"),
            patch("apps.tasks.tasks.TaskScheduler"),
            patch("apps.tasks.tasks.TASK_FUNCTIONS", {}),
            contextlib.suppress(Exception),
        ):
            call_command(
                "run_dispatcherd",
                "--workers",
                "8",
                "--timeout",
                "7200",
                "--max-tasks",
                "200",
                "--log-level",
                "DEBUG",
                stdout=self.stdout,
            )

        output = self.stdout.getvalue()
        self.assertIn("Starting dispatcherd with 8 workers", output)

    def test_invalid_log_level(self):
        """Test command with invalid log level."""
        with self.assertRaises(CommandError):
            call_command("run_dispatcherd", "--log-level", "INVALID", stdout=self.stdout, stderr=StringIO())

    def test_help_output(self):
        """Test command help output."""
        import sys
        from io import StringIO

        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            with self.assertRaises(SystemExit):
                call_command("run_dispatcherd", "--help")
        finally:
            sys.stdout = old_stdout

        output = captured_output.getvalue()
        self.assertIn("Run dispatcherd background task worker", output)
        self.assertIn("--workers", output)
        self.assertIn("--timeout", output)
        self.assertIn("--max-tasks", output)
        self.assertIn("--log-level", output)


@pytest.mark.unit
class TestRunDispatcherdIntegration(TestCase):
    """Integration tests for run_dispatcherd command."""

    def setUp(self):
        """Set up test fixtures."""
        self.stdout = StringIO()

    def tearDown(self):
        """Clean up test fixtures."""
        # Ensure file handles are properly closed
        if hasattr(self, "stdout") and not self.stdout.closed:
            self.stdout.close()

    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_dispatcherd_config_structure(self, mock_logger):
        """Test that dispatcherd config has correct structure."""
        command = Command()
        command.stdout = self.stdout

        options = {"workers": 3, "timeout": 2400, "max_tasks": 75, "log_level": "DEBUG"}

        captured_config = {}

        def capture_config(config: dict):
            nonlocal captured_config
            captured_config = config

        with (
            patch("dispatcherd.config.setup", side_effect=capture_config),
            patch("dispatcherd.run_service"),
            patch("threading.Thread"),
            patch("apps.tasks.tasks.TaskScheduler"),
            patch("apps.tasks.tasks.TASK_FUNCTIONS", {"task1": Mock(), "task2": Mock()}),
            override_settings(
                DATABASES={
                    "default": {
                        "NAME": "integration_db",
                        "USER": "integration_user",
                        "PASSWORD": "integration_pass",
                        "HOST": "integration_host",
                        "PORT": "5434",
                    }
                }
            ),
        ):
            command.handle(**options)

        # Verify config structure
        self.assertIsNotNone(captured_config)
        self.assertEqual(captured_config["version"], 2)

        # Verify broker config
        self.assertIn("brokers", captured_config)
        self.assertIn("pg_notify", captured_config["brokers"])

        pg_notify = captured_config["brokers"]["pg_notify"]
        self.assertIn("config", pg_notify)
        self.assertIn("channels", pg_notify)

        # Verify database config
        db_config = pg_notify["config"]
        self.assertEqual(db_config["dbname"], "integration_db")
        self.assertEqual(db_config["user"], "integration_user")
        self.assertEqual(db_config["password"], "integration_pass")
        self.assertEqual(db_config["host"], "integration_host")
        self.assertEqual(db_config["port"], "5434")

        # Verify channels
        channels = pg_notify["channels"]
        expected_channels = ["metrics_tasks", "metrics_cleanup", "metrics_notifications"]
        self.assertEqual(channels, expected_channels)

        # Verify service config
        self.assertIn("service", captured_config)
        service_config = captured_config["service"]
        self.assertIn("pool_kwargs", service_config)
        self.assertEqual(service_config["pool_kwargs"]["max_workers"], 3)

    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_exception_during_dispatcherd_setup(self, mock_logger):
        """Test exception handling during dispatcherd.config.setup."""
        command = Command()
        command.stdout = self.stdout

        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        setup_error = Exception("Config setup failed")

        with (
            patch("dispatcherd.config.setup", side_effect=setup_error),
            patch("threading.Thread"),
            patch("apps.tasks.tasks.TaskScheduler"),
            patch("apps.tasks.tasks.TASK_FUNCTIONS", {}),
        ):
            command.handle(**options)

        # Verify exception was logged and handled
        mock_logger.error.assert_called_with("Failed to start dispatcherd: Config setup failed")

        output = self.stdout.getvalue()
        self.assertIn("Start failed: Config setup failed", output)

    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_exception_during_scheduler_start(self, mock_logger):
        """Test exception handling during TaskScheduler creation."""
        command = Command()
        command.stdout = self.stdout

        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        scheduler_error = Exception("Scheduler creation failed")

        with (
            patch("apps.tasks.tasks.TaskScheduler", side_effect=scheduler_error),
            patch("dispatcherd.config.setup"),
            patch("apps.tasks.tasks.TASK_FUNCTIONS", {}),
        ):
            command.handle(**options)

        # Verify exception was logged and handled
        mock_logger.error.assert_called_with("Failed to start dispatcherd: Scheduler creation failed")

        output = self.stdout.getvalue()
        self.assertIn("Start failed: Scheduler creation failed", output)


@pytest.mark.unit
class TestRunDispatcherdEdgeCases(TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.stdout = StringIO()
        self.command.stdout = self.stdout

    def tearDown(self):
        """Clean up test fixtures."""
        # Ensure file handles are properly closed
        if hasattr(self, "stdout") and not self.stdout.closed:
            self.stdout.close()

    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_missing_database_config(self, mock_logger):
        """Test behavior when database config is missing."""
        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        with override_settings(DATABASES={}):
            self.command.handle(**options)

        # Should fail with KeyError and be caught as general exception
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        self.assertIn("Failed to start dispatcherd:", error_call)

    def test_zero_workers(self):
        """Test command with zero workers."""
        options = {"workers": 0, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        captured_config = {}

        def capture_config(config):
            nonlocal captured_config
            captured_config = config

        with (
            patch("dispatcherd.config.setup", side_effect=capture_config),
            patch("dispatcherd.run_service"),
            patch("threading.Thread"),
            patch("apps.tasks.tasks.TaskScheduler"),
            patch("apps.tasks.tasks.TASK_FUNCTIONS", {}),
        ):
            self.command.handle(**options)

        # Verify zero workers is passed through
        self.assertEqual(captured_config["service"]["pool_kwargs"]["max_workers"], 0)

    def test_negative_arguments(self):
        """Test command behavior with negative argument values."""
        # This would typically be caught by argument parser, but test the internal handling
        options = {"workers": -1, "timeout": -100, "max_tasks": -50, "log_level": "INFO"}

        captured_config = {}

        def capture_config(config):
            nonlocal captured_config
            captured_config = config

        with (
            patch("dispatcherd.config.setup", side_effect=capture_config),
            patch("dispatcherd.run_service"),
            patch("threading.Thread"),
            patch("apps.tasks.tasks.TaskScheduler"),
            patch("apps.tasks.tasks.TASK_FUNCTIONS", {}),
        ):
            self.command.handle(**options)

        # Verify negative values are passed through (dispatcherd should handle validation)
        self.assertEqual(captured_config["service"]["pool_kwargs"]["max_workers"], -1)

    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_import_error_specific_modules(self, mock_logger):
        """Test import errors for specific modules."""
        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        # Test specific import failures
        import_errors = [
            "dispatcherd",
            "dispatcherd.config",
            "apps.tasks.tasks",
        ]

        for module_name in import_errors:
            with patch("builtins.__import__", side_effect=ImportError(f"No module named '{module_name}'")):
                self.command.handle(**options)

            # Verify specific import error was logged
            expected_error = f"Failed to import dispatcherd: No module named '{module_name}'"
            mock_logger.error.assert_any_call(expected_error)

            mock_logger.reset_mock()

    @patch("dispatcherd.run_service", side_effect=Exception("Service start failed"))
    @patch("dispatcherd.config.setup")
    @patch("threading.Thread")
    @patch("apps.tasks.tasks.TaskScheduler")
    @patch("apps.tasks.tasks.TASK_FUNCTIONS", {})
    @patch("apps.tasks.management.commands.run_dispatcherd.logger")
    def test_service_start_exception_coverage(
        self, mock_logger, mock_task_scheduler, mock_thread, mock_dispatcherd_setup, mock_run_service
    ):
        """Test exception handling during dispatcherd.run_service() call (lines 116-121)."""
        options = {"workers": 4, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}

        with override_settings(
            DATABASES={
                "default": {
                    "NAME": "test_db",
                    "USER": "test_user",
                    "PASSWORD": "test_pass",
                    "HOST": "localhost",
                    "PORT": "5432",
                }
            }
        ):
            self.command.handle(**options)

        # Verify exception was caught and logged (lines 120-121)
        mock_logger.error.assert_called_with("Failed to start dispatcherd: Service start failed")

        # Verify error message was displayed
        output = self.stdout.getvalue()
        self.assertIn("Start failed: Service start failed", output)
