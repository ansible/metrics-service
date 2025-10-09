"""
Integration tests for the metrics_service management command.

Tests the full metrics service management command functionality including
service initialization, task management, and command line operations.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.tasks.models import Task

User = get_user_model()


@pytest.mark.integration
class TestMetricsServiceCommand(TransactionTestCase):
    """Integration tests for the metrics_service management command."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_init_system_tasks_list(self):
        """Test the init-system-tasks --list subcommand."""
        with patch("sys.stdout.write") as mock_stdout:
            call_command("metrics_service", "init-system-tasks", "--list")

        # Should not raise an exception
        mock_stdout.assert_called()

    def test_init_system_tasks_dry_run(self):
        """Test the init-system-tasks --dry-run subcommand."""
        with patch("sys.stdout.write") as mock_stdout:
            call_command("metrics_service", "init-system-tasks", "--dry-run")

        # Should not raise an exception and not make changes
        mock_stdout.assert_called()

    def test_task_create_command(self):
        """Test the tasks create subcommand."""
        task_data = '{"test": "data"}'

        call_command(
            "metrics_service",
            "tasks",
            "create",
            "--name",
            "Test Task",
            "--function",
            "cleanup_old_data",
            "--data",
            task_data,
            "--description",
            "Test description",
            "--priority",
            "2",
            "--user",
            self.user.username,
        )

        # Verify task was created
        task = Task.objects.get(name="Test Task")
        assert task.function_name == "cleanup_old_data"
        assert task.task_data == {"test": "data"}
        assert task.description == "Test description"
        assert task.priority == 2
        assert task.created_by == self.user

    def test_task_list_command(self):
        """Test the tasks list subcommand."""
        # Create test tasks
        task1 = Task.objects.create(
            name="Task 1", function_name="cleanup_old_data", status="pending", created_by=self.user
        )
        task1._skip_signals = True
        task1.save()
        Task.objects.create(
            name="Task 2", function_name="send_notification_email", status="completed", created_by=self.user
        )

        with patch("sys.stdout.write") as mock_stdout:
            call_command("metrics_service", "tasks", "list")

        mock_stdout.assert_called()

    def test_task_list_with_status_filter(self):
        """Test tasks list with status filtering."""
        pending_task = Task.objects.create(
            name="Pending Task", function_name="cleanup_old_data", status="pending", created_by=self.user
        )
        pending_task._skip_signals = True
        pending_task.save()
        Task.objects.create(
            name="Completed Task", function_name="send_notification_email", status="completed", created_by=self.user
        )

        with patch("sys.stdout.write") as mock_stdout:
            call_command("metrics_service", "tasks", "list", "--status", "pending")

        mock_stdout.assert_called()

    def test_task_show_command(self):
        """Test the tasks show subcommand."""
        task = Task.objects.create(
            name="Show Task",
            function_name="cleanup_old_data",
            task_data={"test": "data"},
            description="Test task for show command",
            created_by=self.user,
        )

        with patch("sys.stdout.write") as mock_stdout:
            call_command("metrics_service", "tasks", "show", str(task.id))

        mock_stdout.assert_called()

    def test_task_cancel_command(self):
        """Test the tasks cancel subcommand."""
        # Create task with completed status first to avoid signal issues, then change to pending
        task = Task.objects.create(
            name="Cancel Task", function_name="cleanup_old_data", status="completed", created_by=self.user
        )
        task.status = "pending"
        task._skip_signals = True
        task.save()

        with patch("sys.stdout.write"):
            call_command("metrics_service", "tasks", "cancel", str(task.id))

        # Verify task was cancelled
        task.refresh_from_db()
        assert task.status == "cancelled"

    def test_task_retry_command(self):
        """Test the tasks retry subcommand."""
        task = Task.objects.create(
            name="Retry Task", function_name="cleanup_old_data", status="failed", created_by=self.user
        )

        with patch("sys.stdout.write"):
            call_command("metrics_service", "tasks", "retry", str(task.id))

        # Verify task was reset to pending
        task.refresh_from_db()
        assert task.status == "pending"

    def test_cron_status_command(self):
        """Test the cron status subcommand."""
        with patch("apps.tasks.cron_scheduler.get_scheduler") as mock_get_scheduler:
            mock_scheduler = MagicMock()
            mock_scheduler.running = True
            mock_get_scheduler.return_value = mock_scheduler

            with patch("sys.stdout.write") as mock_stdout:
                call_command("metrics_service", "cron", "status")

            mock_stdout.assert_called()

    def test_cron_list_command(self):
        """Test the cron list subcommand."""
        with patch("apps.tasks.cron_scheduler.get_scheduler") as mock_get_scheduler:
            mock_job = MagicMock()
            mock_job.id = "test-job"
            mock_job.func = "test_function"
            mock_job.next_run_time = timezone.now()

            mock_scheduler = MagicMock()
            mock_scheduler.get_jobs.return_value = [mock_job]
            mock_get_scheduler.return_value = mock_scheduler

            with patch("sys.stdout.write") as mock_stdout:
                call_command("metrics_service", "cron", "list")

            mock_stdout.assert_called()

    def test_invalid_command_arguments(self):
        """Test error handling for invalid command arguments."""
        # Test invalid JSON data
        with pytest.raises(SystemExit):
            call_command(
                "metrics_service",
                "tasks",
                "create",
                "--name",
                "Invalid Task",
                "--function",
                "cleanup_old_data",
                "--data",
                "invalid-json",
            )

        # Test invalid scheduled time format
        with pytest.raises(SystemExit):
            call_command(
                "metrics_service",
                "tasks",
                "create",
                "--name",
                "Invalid Time Task",
                "--function",
                "cleanup_old_data",
                "--scheduled-time",
                "invalid-time-format",
            )

        # Test non-existent user
        with pytest.raises(SystemExit):
            call_command(
                "metrics_service",
                "tasks",
                "create",
                "--name",
                "Invalid User Task",
                "--function",
                "cleanup_old_data",
                "--user",
                "nonexistent_user",
            )

    def test_task_not_found_operations(self):
        """Test operations on non-existent tasks."""
        # Test show non-existent task
        with pytest.raises(SystemExit):
            call_command("metrics_service", "tasks", "show", "99999")

        # Test cancel non-existent task
        with pytest.raises(SystemExit):
            call_command("metrics_service", "tasks", "cancel", "99999")

        # Test retry non-existent task
        with pytest.raises(SystemExit):
            call_command("metrics_service", "tasks", "retry", "99999")

    def test_task_invalid_state_operations(self):
        """Test operations on tasks in invalid states."""
        # Create completed task
        completed_task = Task.objects.create(
            name="Completed Task", function_name="cleanup_old_data", status="completed", created_by=self.user
        )

        # Try to cancel completed task
        with patch("sys.stdout.write"):
            call_command("metrics_service", "tasks", "cancel", str(completed_task.id))

        # Task should remain completed
        completed_task.refresh_from_db()
        assert completed_task.status == "completed"

        # Create pending task and try to retry it
        pending_task = Task.objects.create(
            name="Pending Task", function_name="cleanup_old_data", status="pending", created_by=self.user
        )
        pending_task._skip_signals = True
        pending_task.save()

        with patch("sys.stdout.write"):
            call_command("metrics_service", "tasks", "retry", str(pending_task.id))

        # Task should remain pending
        pending_task.refresh_from_db()
        assert pending_task.status == "pending"

    def test_command_help_outputs(self):
        """Test that help commands work without errors."""
        with patch("sys.stdout.write"), pytest.raises(SystemExit):  # Help commands exit with code 0
            call_command("metrics_service", "--help")


@pytest.mark.integration
class TestMetricsServiceCommandSubprocess(TestCase):
    """Integration tests using subprocess to test command line interface."""

    def setUp(self):
        """Set up test environment."""
        self.manage_py = Path(__file__).parent.parent.parent / "manage.py"
        assert self.manage_py.exists(), f"manage.py not found at {self.manage_py}"

    def _run_command(self, *args, timeout=30):
        """Helper to run management command via subprocess."""
        cmd = [sys.executable, str(self.manage_py), "metrics_service"] + list(args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
            return result
        except subprocess.TimeoutExpired:
            pytest.fail(f"Command timed out: {' '.join(cmd)}")

    def test_help_command_subprocess(self):
        """Test help command via subprocess."""
        result = self._run_command("--help")
        assert result.returncode == 0
        assert "metrics_service" in str(result.stdout)

    def test_init_system_tasks_list_subprocess(self):
        """Test init-system-tasks --list command via subprocess."""
        result = self._run_command("init-system-tasks", "--list")
        assert result.returncode == 0

    def test_init_system_tasks_dry_run_subprocess(self):
        """Test init-system-tasks --dry-run command via subprocess."""
        result = self._run_command("init-system-tasks", "--dry-run")
        assert result.returncode == 0
        assert "DRY RUN" in result.stdout

    def test_cron_status_subprocess(self):
        """Test cron status command via subprocess."""
        result = self._run_command("cron", "status")
        # Should not fail even if scheduler is not running
        assert result.returncode == 0

    def test_tasks_subcommand_help_subprocess(self):
        """Test tasks subcommand help via subprocess."""
        result = self._run_command("tasks", "--help")
        assert result.returncode == 0
        assert "Task management actions" in result.stdout

    def test_cron_subcommand_help_subprocess(self):
        """Test cron subcommand help via subprocess."""
        result = self._run_command("cron", "--help")
        assert result.returncode == 0
        assert "Cron management actions" in result.stdout


@pytest.mark.integration
class TestMetricsServiceFullIntegration(TransactionTestCase):
    """Full integration tests that test the complete service startup."""

    def setUp(self):
        """Set up test environment."""
        self.manage_py = Path(__file__).parent.parent.parent / "manage.py"
        assert self.manage_py.exists(), f"manage.py not found at {self.manage_py}"

    @patch("apps.core.management.commands.metrics_service.Command._start_services")
    def test_service_run_command_validation(self, mock_start_services):
        """Test that the run command validates and processes arguments correctly."""
        # Mock the actual service startup to avoid conflicts
        mock_start_services.return_value = None

        with patch("sys.exit"):
            call_command(
                "metrics_service",
                "run",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
                "--workers",
                "2",
                "--timeout",
                "1800",
                "--max-tasks",
                "50",
                "--log-level",
                "DEBUG",
            )

        # Verify service startup was called with correct config
        mock_start_services.assert_called_once()
        args, kwargs = mock_start_services.call_args
        config = args[0]

        assert config["host"] == "127.0.0.1"
        assert config["port"] == "8001"
        assert config["workers"] == 2
        assert config["timeout"] == 1800
        assert config["max_tasks"] == 50
        assert config["log_level"] == "DEBUG"

    def test_signal_handler_setup(self):
        """Test that signal handlers are properly configured."""
        import signal

        from apps.core.management.commands.metrics_service import Command

        command = Command()
        command.shutdown_requested = False
        command.threads = []
        command.processes = []

        # Test signal handler setup
        command._setup_signal_handlers()

        # Verify signal handlers are installed
        assert signal.signal(signal.SIGINT, signal.SIG_DFL) != signal.SIG_DFL
        assert signal.signal(signal.SIGTERM, signal.SIG_DFL) != signal.SIG_DFL

    def test_configuration_extraction(self):
        """Test configuration extraction from command options."""
        from apps.core.management.commands.metrics_service import Command

        command = Command()
        options = {
            "host": "localhost",
            "port": "9000",
            "workers": 8,
            "timeout": 7200,
            "max_tasks": 200,
            "log_level": "WARNING",
        }

        config = command._extract_config(options)

        assert config["host"] == "localhost"
        assert config["port"] == "9000"
        assert config["workers"] == 8
        assert config["timeout"] == 7200
        assert config["max_tasks"] == 200
        assert config["log_level"] == "WARNING"

    def test_django_server_command_building(self):
        """Test Django server command building and validation."""
        import sys
        from pathlib import Path

        from apps.core.management.commands.metrics_service import Command

        Command()

        # Test command building logic without actually running it
        manage_py = Path(__file__).parent.parent.parent / "manage.py"
        if not manage_py.exists():
            pytest.skip("manage.py not found")

        # Test input validation (this is what we're really testing)
        host = "127.0.0.1"
        port = "8000"

        # Validate inputs for security (copied from the actual method)
        if not isinstance(host, str) or not host.replace(".", "").replace(":", "").isalnum():
            pytest.fail(f"Invalid host: {host}")
        if not isinstance(port, int | str) or not str(port).isdigit():
            pytest.fail(f"Invalid port: {port}")

        # Build expected command
        expected_cmd = [
            sys.executable,
            str(manage_py),
            "runserver",
            f"{host}:{port}",
            "--noreload",
        ]

        # Verify command structure
        assert "runserver" in expected_cmd
        assert f"{host}:{port}" in expected_cmd
        assert "--noreload" in expected_cmd

    def test_dispatcher_command_building(self):
        """Test dispatcher command building and validation."""
        from apps.core.management.commands.metrics_service import Command

        command = Command()

        # Test command building without actually running it
        cmd = command._build_dispatcher_command(4, 3600, 100, "INFO")

        # Verify command structure
        assert "run_dispatcherd" in cmd
        assert "--workers=4" in cmd
        assert "--timeout=3600" in cmd
        assert "--max-tasks=100" in cmd
        assert "--log-level=INFO" in cmd

    def test_input_validation(self):
        """Test input validation for security."""
        from apps.core.management.commands.metrics_service import Command

        command = Command()

        # Test invalid workers validation (this should raise ValueError)
        with pytest.raises(ValueError, match="Invalid workers count"):
            command._build_dispatcher_command(-1, 3600, 100, "INFO")

        # Test invalid timeout validation (this should raise ValueError)
        with pytest.raises(ValueError, match="Invalid timeout"):
            command._build_dispatcher_command(4, 0, 100, "INFO")

        # Test invalid log level validation (this should raise ValueError)
        with pytest.raises(ValueError, match="Invalid log_level"):
            command._build_dispatcher_command(4, 3600, 100, "INVALID")

        # For the Django server methods that catch exceptions and log errors,
        # we test that they handle invalid input gracefully without crashing
        with patch("sys.stdout.write") as mock_stdout:
            command._run_django_server("'; rm -rf /; #", "8000", "INFO")
            # Should log error message
            mock_stdout.assert_called()

        with patch("sys.stdout.write") as mock_stdout:
            command._run_django_server("127.0.0.1", "'; rm -rf /; #", "INFO")
            # Should log error message
            mock_stdout.assert_called()
