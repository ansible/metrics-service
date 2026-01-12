"""
Integration tests for apps.core.management.commands.metrics_service module.
"""

import signal
import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from django.test import TestCase

from apps.tasks.management.commands.metrics_service import Command


class TestMetricsServiceCommand(TestCase):
    """Test metrics_service management command."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.out = StringIO()
        self.err = StringIO()
        self.command.shutdown_requested = False

    def tearDown(self):
        """Clean up test fixtures."""
        # Ensure shutdown is requested to stop any running processes
        self.command.shutdown_requested = True
        # Clean up any processes or threads that might be running
        if hasattr(self.command, "_cleanup_processes_and_threads"):
            self.command._cleanup_processes_and_threads()

    def test_command_help_text(self):
        """Test command has proper help text."""
        assert self.command.help == "Metrics service management - unified entry point for all service operations"

    def test_add_arguments(self):
        """Test add_arguments method configures parser correctly."""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        self.command.add_arguments(parser)

        # Test that subcommands are added
        actions = {action.dest: action for action in parser._actions}

        assert "command" in actions
        assert hasattr(actions["command"], "choices")
        assert "run" in actions["command"].choices
        assert "init-service-id" in actions["command"].choices
        assert "init-system-tasks" in actions["command"].choices
        assert "tasks" in actions["command"].choices
        assert "cron" in actions["command"].choices

    def test_extract_config(self):
        """Test _extract_config method."""
        options = {
            "host": "localhost",
            "port": "9000",
            "workers": 8,
            "timeout": 7200,
            "max_tasks": 200,
            "log_level": "DEBUG",
        }

        config = self.command._extract_config(options)

        assert config == {
            "host": "localhost",
            "port": "9000",
            "workers": 8,
            "timeout": 7200,
            "max_tasks": 200,
            "log_level": "DEBUG",
        }

    @patch("signal.signal")
    def test_setup_signal_handlers(self, mock_signal):
        """Test _setup_signal_handlers method."""
        self.command.stdout = self.out
        self.command._setup_signal_handlers()

        # Verify signal handlers were registered
        mock_signal.assert_has_calls(
            [
                call(signal.SIGINT, mock_signal.call_args_list[0][0][1]),
                call(signal.SIGTERM, mock_signal.call_args_list[1][0][1]),
            ]
        )

    @patch("subprocess.Popen")
    @patch("signal.signal")
    @patch("pathlib.Path.exists")
    @patch("time.sleep")
    @patch("sys.exit")
    def test_start_services_success(self, mock_exit, mock_sleep, mock_exists, mock_signal, mock_popen):
        """Test _start_services method success path."""
        self.command.stdout = self.out
        # Update the output formatter to use the test stdout
        self.command.output.stdout = self.out

        # Mock Path.exists to return True for manage.py
        mock_exists.return_value = True

        # Make sys.exit raise SystemExit (like the real sys.exit does)
        # This is necessary because the implementation uses an infinite loop
        # that only exits via sys.exit(), and if sys.exit doesn't raise,
        # the loop will hang forever
        mock_exit.side_effect = SystemExit

        # Track poll calls to simulate process exit after first monitoring iteration
        poll_call_count = {"django": 0}

        def django_poll_side_effect():
            """Simulate Django process that exits after first monitoring check."""
            poll_call_count["django"] += 1
            # First call in monitoring loop returns None (running)
            # Second call (when checking if exited) returns 0 (exited)
            # Subsequent calls during cleanup should return 0
            if poll_call_count["django"] == 1:
                return None  # First check: still running
            return 0  # Exited

        # Create separate mock processes for each service
        django_process = MagicMock()
        django_process.poll.side_effect = django_poll_side_effect
        django_process.returncode = 0
        django_process.terminate.return_value = None
        django_process.kill.return_value = None

        # Other processes stay running (always return None)
        other_process = MagicMock()
        other_process.poll.return_value = None
        other_process.terminate.return_value = None
        other_process.kill.return_value = None

        # Return different processes for each call
        mock_popen.side_effect = [django_process, other_process, other_process]

        config = {
            "host": "127.0.0.1",
            "port": "8000",
            "workers": 4,
            "log_level": "INFO",
            "timeout": 3600,
            "max_tasks": 100,
        }

        # Make sleep do nothing to speed up test
        mock_sleep.return_value = None

        # sys.exit will raise SystemExit, which we need to catch
        with pytest.raises(SystemExit):
            self.command._start_services(config)

        # Should exit when process exits
        mock_exit.assert_called()

        # Verify processes were started (3 processes: Django, Dispatcher, Scheduler)
        assert mock_popen.call_count == 3

        # Check output contains startup message
        output = self.out.getvalue()
        assert "Starting metrics service:" in output
        assert "Django server: http://127.0.0.1:8000" in output
        assert "Dispatcher workers: 4" in output

    @patch("pathlib.Path.exists")
    @patch("sys.exit")
    def test_start_services_exception(self, mock_exit, mock_exists):
        """Test _start_services handles exceptions."""
        self.command.stdout = self.out
        # Update the output formatter to use the test stdout
        self.command.output.stdout = self.out

        # Mock Path.exists to raise an exception (simulating an error during startup)
        mock_exists.side_effect = Exception("Test error")

        config = {
            "host": "127.0.0.1",
            "port": "8000",
            "workers": 4,
            "log_level": "INFO",
            "timeout": 3600,
            "max_tasks": 100,
        }

        self.command._start_services(config)

        mock_exit.assert_called_once_with(1)

        output = self.out.getvalue()
        assert "Failed to start services: Test error" in output

    @patch.object(Command, "_handle_run_command")
    def test_handle_method(self, mock_run_command):
        """Test handle method orchestration."""
        options = {"command": "run", "host": "127.0.0.1", "port": "8000", "workers": 4}

        self.command.handle(**options)

        # Verify the run command handler was called
        mock_run_command.assert_called_once_with(options)


class TestMetricsServiceSignalHandling(TestCase):
    """Test signal handling functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.command.stdout = StringIO()

class TestMetricsServiceEdgeCases(TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.out = StringIO()
        self.command.stdout = self.out
        self.command.shutdown_requested = False

    def tearDown(self):
        """Clean up test fixtures."""
        # Ensure shutdown is requested to stop any running processes
        self.command.shutdown_requested = True
