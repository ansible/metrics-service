"""
Comprehensive tests for run_task_scheduler management command.

This module provides complete test coverage for the run_task_scheduler command,
testing all code paths including success cases, error handling, and interrupt handling.
"""

import contextlib
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase


@pytest.mark.unit
class TestRunTaskSchedulerCommand(TestCase):
    """Test cases for run_task_scheduler management command."""

    def test_add_arguments_method(self):
        """Test that add_arguments properly configures command line arguments."""
        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        parser = MagicMock()

        command.add_arguments(parser)

        # Verify that arguments were added
        assert parser.add_argument.call_count == 2

        # Check log-level argument
        first_call = parser.add_argument.call_args_list[0]
        assert first_call[0][0] == "--log-level"
        assert first_call[1]["choices"] == ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert first_call[1]["default"] == "INFO"

        # Check check-interval argument
        second_call = parser.add_argument.call_args_list[1]
        assert second_call[0][0] == "--check-interval"
        assert second_call[1]["type"] is int
        assert second_call[1]["default"] == 60

    def test_command_help_text(self):
        """Test that command has proper help text."""
        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        assert command.help == "Run the task scheduler for cron-based recurring tasks"

    def test_basic_command_execution(self):
        """Test basic command execution."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        # Mock scheduler and related functions
        mock_scheduler = MagicMock()
        mock_scheduler.running = False  # This will cause the loop to exit immediately

        with (
            patch("apps.tasks.cron_scheduler.get_scheduler", return_value=mock_scheduler),
            patch("apps.tasks.cron_scheduler.start_scheduler"),
            patch("time.sleep"),
            patch("logging.basicConfig"),
        ):
            command.handle(log_level="INFO", check_interval=60)

        output = out.getvalue()
        assert "Starting task scheduler (check interval: 60s)" in output
        assert "Task scheduler started successfully" in output
        assert "Scheduler stopped unexpectedly" in output

    def test_command_with_debug_log_level(self):
        """Test command execution with DEBUG log level."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        with (
            patch("apps.tasks.cron_scheduler.get_scheduler", return_value=mock_scheduler),
            patch("apps.tasks.cron_scheduler.start_scheduler"),
            patch("time.sleep"),
            patch("logging.basicConfig") as mock_basic_config,
        ):
            command.handle(log_level="DEBUG", check_interval=30)

            # Verify logging was configured with DEBUG level
            mock_basic_config.assert_called_once_with(level=logging.DEBUG)

        output = out.getvalue()
        assert "Starting task scheduler (check interval: 30s)" in output

    def test_command_with_custom_check_interval(self):
        """Test command execution with custom check interval."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        with (
            patch("apps.tasks.cron_scheduler.get_scheduler", return_value=mock_scheduler),
            patch("apps.tasks.cron_scheduler.start_scheduler"),
            patch("time.sleep") as mock_sleep,
            patch("logging.basicConfig"),
        ):
            command.handle(log_level="INFO", check_interval=120)

            # Verify sleep was called with correct interval
            mock_sleep.assert_called_once_with(120)

        output = out.getvalue()
        assert "Starting task scheduler (check interval: 120s)" in output

    def test_keyboard_interrupt_handling(self):
        """Test handling of KeyboardInterrupt."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        # Make time.sleep raise KeyboardInterrupt on first call
        def sleep_side_effect(*args):
            raise KeyboardInterrupt()

        with (
            patch("apps.tasks.cron_scheduler.get_scheduler", return_value=mock_scheduler),
            patch("apps.tasks.cron_scheduler.start_scheduler"),
            patch("apps.tasks.cron_scheduler.stop_scheduler") as mock_stop,
            patch("time.sleep", side_effect=sleep_side_effect),
            patch("logging.basicConfig"),
        ):
            command.handle(log_level="INFO", check_interval=60)

            # Verify stop_scheduler was called
            mock_stop.assert_called_once()

        output = out.getvalue()
        assert "Received interrupt signal, stopping scheduler..." in output
        assert "Task scheduler stopped" in output

    def test_import_error_handling(self):
        """Test handling of ImportError when importing scheduler."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        # Make the import raise ImportError
        with (
            patch("apps.tasks.cron_scheduler.get_scheduler", side_effect=ImportError("Module not found")),
            patch("logging.basicConfig"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                command.handle(log_level="INFO", check_interval=60)

            assert exc_info.value.code == 1

        output = out.getvalue()
        assert "Failed to import scheduler:" in output
        assert "Module not found" in output

    def test_general_exception_handling(self):
        """Test handling of general exceptions."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        # Make start_scheduler raise a general exception
        with (
            patch("apps.tasks.cron_scheduler.start_scheduler", side_effect=RuntimeError("Scheduler error")),
            patch("logging.basicConfig"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                command.handle(log_level="INFO", check_interval=60)

            assert exc_info.value.code == 1

        output = out.getvalue()
        assert "Failed to start task scheduler:" in output
        assert "Scheduler error" in output

    def test_all_log_levels(self):
        """Test that all log levels can be configured."""
        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = StringIO()

        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        log_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        expected_levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]

        for log_level, expected_level in zip(log_levels, expected_levels, strict=False):
            with (
                patch("apps.tasks.cron_scheduler.get_scheduler", return_value=mock_scheduler),
                patch("apps.tasks.cron_scheduler.start_scheduler"),
                patch("time.sleep"),
                patch("logging.basicConfig") as mock_basic_config,
            ):
                command.handle(log_level=log_level, check_interval=60)

                # Verify logging was configured with correct level
                mock_basic_config.assert_called_with(level=expected_level)

    def test_scheduler_stop_during_execution(self):
        """Test scheduler stopping unexpectedly during execution."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        mock_scheduler = MagicMock()
        # Start with running=True, then set to False after first sleep
        mock_scheduler.running = True

        call_count = [0]

        def sleep_side_effect(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                # After first sleep, mark scheduler as stopped
                mock_scheduler.running = False

        with (
            patch("apps.tasks.cron_scheduler.get_scheduler", return_value=mock_scheduler),
            patch("apps.tasks.cron_scheduler.start_scheduler"),
            patch("time.sleep", side_effect=sleep_side_effect),
            patch("logging.basicConfig"),
        ):
            command.handle(log_level="INFO", check_interval=60)

        output = out.getvalue()
        assert "Scheduler stopped unexpectedly" in output

    def test_module_has_logger(self):
        """Test that module has logger attribute."""
        from apps.tasks.management.commands import run_task_scheduler

        assert hasattr(run_task_scheduler, "logger")
        assert isinstance(run_task_scheduler.logger, logging.Logger)

    def test_command_class_attributes(self):
        """Test that Command class has expected attributes."""
        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        assert hasattr(command, "help")
        assert hasattr(command, "add_arguments")
        assert hasattr(command, "handle")

    def test_sys_exit_on_import_error(self):
        """Test that sys.exit is called on ImportError."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        with (
            patch("apps.tasks.cron_scheduler.start_scheduler", side_effect=ImportError("Missing module")),
            patch("logging.basicConfig"),
            patch("sys.exit") as mock_exit,
        ):
            with contextlib.suppress(SystemExit):
                command.handle(log_level="INFO", check_interval=60)

            mock_exit.assert_called_once_with(1)

    def test_sys_exit_on_general_exception(self):
        """Test that sys.exit is called on general exceptions."""
        out = StringIO()

        from apps.tasks.management.commands.run_task_scheduler import Command

        command = Command()
        command.stdout = out

        with (
            patch("apps.tasks.cron_scheduler.start_scheduler", side_effect=ValueError("Invalid value")),
            patch("logging.basicConfig"),
            patch("sys.exit") as mock_exit,
        ):
            with contextlib.suppress(SystemExit):
                command.handle(log_level="INFO", check_interval=60)

            mock_exit.assert_called_once_with(1)
