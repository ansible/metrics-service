"""
Integration tests for apps.core.management.commands.metrics_service module.
"""

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import TestCase

from apps.tasks.management.commands.metrics_service import Command
from tests.unit.core.test_metrics_service_helpers import create_mock_processes_with_exit, get_default_config


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
    @patch("subprocess.Popen")
    @patch("pathlib.Path.exists")
    @patch("time.sleep")
    @patch("sys.exit")
    def test_signal_handlers_in_start_services(self, mock_exit, mock_sleep, mock_exists, mock_popen, mock_signal):
        """Test that signal handlers are set up in _start_services_simple."""
        self.command.stdout = self.out
        self.command.output.stdout = self.out

        mock_exists.return_value = True
        mock_exit.side_effect = SystemExit
        mock_sleep.return_value = None
        mock_popen.side_effect = create_mock_processes_with_exit()

        config = get_default_config()

        # Signal handlers are set up inside _start_services_simple
        # We'll verify they're called when the method runs
        with pytest.raises(SystemExit):
            self.command._start_services(config)

        # Verify signal handlers were registered (called twice for SIGINT and SIGTERM)
        assert mock_signal.call_count >= 2

    @patch("subprocess.Popen")
    @patch("signal.signal")
    @patch("pathlib.Path.exists")
    @patch("time.sleep")
    @patch("sys.exit")
    def test_start_services_success(self, mock_exit, mock_sleep, mock_exists, mock_signal, mock_popen):
        """Test _start_services method success path."""
        self.command.stdout = self.out
        self.command.output.stdout = self.out

        mock_exists.return_value = True
        mock_exit.side_effect = SystemExit
        mock_sleep.return_value = None
        mock_popen.side_effect = create_mock_processes_with_exit()

        config = get_default_config()

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

    @patch("subprocess.Popen")
    @patch("pathlib.Path.exists")
    @patch("time.sleep")
    @patch("sys.exit")
    def test_start_services_builds_correct_commands(self, mock_exit, mock_sleep, mock_exists, mock_popen):
        """Test that _start_services_simple builds correct commands for all three processes."""
        import sys

        from apps.tasks.management.commands import metrics_service

        self.command.stdout = self.out
        self.command.output.stdout = self.out

        manage_py = Path(__file__).parent.parent.parent.parent / "manage.py"
        # Patch sys.argv[0] in the metrics_service module to point to manage.py
        # so the command finds it correctly when it uses sys.argv[0]
        original_argv = metrics_service.sys.argv
        metrics_service.sys.argv = [str(manage_py)]

        mock_exists.return_value = True
        mock_exit.side_effect = SystemExit
        mock_sleep.return_value = None
        mock_popen.side_effect = create_mock_processes_with_exit()

        config = get_default_config(log_level="DEBUG")

        try:
            with pytest.raises(SystemExit):
                self.command._start_services(config)
        finally:
            # Restore original argv
            metrics_service.sys.argv = original_argv

        # Verify 3 processes were started
        assert mock_popen.call_count == 3

        # Verify Django command
        django_call = mock_popen.call_args_list[0]
        django_cmd = django_call[0][0]
        assert sys.executable in django_cmd
        assert str(manage_py) in django_cmd
        assert "runserver" in django_cmd
        assert "127.0.0.1:8000" in django_cmd
        assert "--noreload" in django_cmd
        assert "--verbosity=2" in django_cmd  # DEBUG level adds verbosity

        # Verify Dispatcher command
        dispatcher_call = mock_popen.call_args_list[1]
        dispatcher_cmd = dispatcher_call[0][0]
        assert sys.executable in dispatcher_cmd
        assert str(manage_py) in dispatcher_cmd
        assert "run_dispatcherd" in dispatcher_cmd
        assert "--workers=4" in dispatcher_cmd
        assert "--timeout=3600" in dispatcher_cmd
        assert "--max-tasks=100" in dispatcher_cmd
        assert "--log-level=DEBUG" in dispatcher_cmd

        # Verify Scheduler command
        scheduler_call = mock_popen.call_args_list[2]
        scheduler_cmd = scheduler_call[0][0]
        assert sys.executable in scheduler_cmd
        assert str(manage_py) in scheduler_cmd
        assert "run_task_scheduler" in scheduler_cmd
        assert "--log-level=DEBUG" in scheduler_cmd


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
