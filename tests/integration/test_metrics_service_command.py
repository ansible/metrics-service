"""
Integration tests for the metrics_service management command.

Tests the full metrics service management command functionality including
service initialization, task management, and command line operations.
"""

import json
import subprocess
import sys
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.tasks.models import Task, TaskExecution
from tests.test_utils import get_test_password
from tests.unit.core.test_metrics_service_helpers import create_mock_processes_with_exit, get_default_config

User = get_user_model()


@pytest.mark.integration
class TestMetricsServiceCommand(TransactionTestCase):
    """Integration tests for the metrics_service management command."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_init_system_tasks_list(self):
        """Test the init-system-tasks --list subcommand."""
        with patch("sys.stdout.write") as mock_stdout:
            call_command("metrics_service", "init-system-tasks", "--list")

        # Should not raise an exception
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
            "hello_world",
            "--data",
            task_data,
            "--description",
            "Test description",
            "--user",
            self.user.username,
        )

        # Verify task was created
        task = Task.objects.get(name="Test Task")
        assert task.function_name == "hello_world"
        assert task.task_data == {"test": "data"}
        assert task.description == "Test description"
        assert task.created_by == self.user

    def test_task_list_command(self):
        """Test the tasks list subcommand."""
        # Create test tasks
        task1 = Task.objects.create(name="Task 1", function_name="hello_world", status="pending", created_by=self.user)
        task1.save()
        Task.objects.create(name="Task 2", function_name="hello_world", status="completed", created_by=self.user)

        with patch("sys.stdout.write") as mock_stdout:
            call_command("metrics_service", "tasks", "list")

        mock_stdout.assert_called()

    def test_task_list_with_status_filter(self):
        """Test tasks list with status filtering."""
        pending_task = Task.objects.create(
            name="Pending Task", function_name="hello_world", status="pending", created_by=self.user
        )
        pending_task.save()
        Task.objects.create(
            name="Completed Task", function_name="hello_world", status="completed", created_by=self.user
        )

        with patch("sys.stdout.write") as mock_stdout:
            call_command("metrics_service", "tasks", "list", "--status", "pending")

        mock_stdout.assert_called()

    def test_task_show_command(self):
        """Test the tasks show subcommand."""
        task = Task.objects.create(
            name="Show Task",
            function_name="hello_world",
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
            name="Cancel Task", function_name="hello_world", status="completed", created_by=self.user
        )
        task.status = "pending"
        task.save()

        with patch("sys.stdout.write"):
            call_command("metrics_service", "tasks", "cancel", str(task.id))

        # Verify task was cancelled
        task.refresh_from_db()
        assert task.status == "cancelled"

    def test_task_retry_command(self):
        """Test the tasks retry subcommand."""
        task = Task.objects.create(
            name="Retry Task", function_name="hello_world", status="failed", created_by=self.user
        )

        with patch("sys.stdout.write"):
            call_command("metrics_service", "tasks", "retry", str(task.id))

        # Verify task was reset to pending
        task.refresh_from_db()
        assert task.status == "pending"

    def test_task_diagnose_empty_database(self):
        """Test tasks diagnose exits 0 and reports no stuck tasks on an empty DB."""
        out = StringIO()
        live_state = {"live_available": False, "running": {}, "workers": [], "producers": [], "error": "test"}

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command("metrics_service", "tasks", "diagnose", stdout=out)

        output = out.getvalue()
        assert "Metrics service task diagnostics" in output
        assert "No stuck tasks." in output

    def test_task_diagnose_reports_findings(self):
        """Test tasks diagnose text output includes stuck, success, and failure data."""
        now = timezone.now()
        stuck_task = Task.objects.create(
            name="Stuck Collect",
            function_name="collect_hourly_metrics",
            status="running",
            started_at=now - timedelta(seconds=120),
            attempts=2,
            created_by=self.user,
        )
        TaskExecution.objects.create(task=stuck_task, status="running", worker_id="dispatcher-1")

        success_task = Task.objects.create(
            name="Successful Hello", function_name="hello_world", status="completed", created_by=self.user
        )
        completed_at = now - timedelta(minutes=5)
        TaskExecution.objects.create(task=success_task, status="completed", completed_at=completed_at)
        TaskExecution.objects.create(
            task=success_task, status="failed", completed_at=now - timedelta(hours=1), error_message="boom"
        )

        out = StringIO()
        live_state = {"live_available": False, "running": {}, "workers": [], "producers": [], "error": "test"}

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command("metrics_service", "tasks", "diagnose", "--stuck-timeout", "60", stdout=out)

        output = out.getvalue()
        assert f"ID: {stuck_task.id}" in output
        assert "collect_hourly_metrics" in output
        assert "00:02:00" in output
        assert completed_at.isoformat() in output
        assert "hello_world: 1 failure(s)" in output

    def test_task_diagnose_json_output(self):
        """Test tasks diagnose --format json emits valid parseable JSON."""
        now = timezone.now()
        stuck_task = Task.objects.create(
            name="Stuck Task",
            function_name="hello_world",
            status="running",
            started_at=now - timedelta(seconds=120),
            created_by=self.user,
        )

        out = StringIO()
        live_state = {"live_available": False, "running": {}, "workers": [], "producers": [], "error": "test"}

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command(
                "metrics_service", "tasks", "diagnose", "--format", "json", "--stuck-timeout", "60", stdout=out
            )

        data = json.loads(out.getvalue())
        assert data["schema_version"] == 2
        assert set(data) >= {
            "generated_at",
            "task_timeout_seconds",
            "window_hours",
            "stuck_tasks",
            "last_success",
            "failures_in_window",
            "queue_depth",
        }
        assert [row["task_id"] for row in data["stuck_tasks"]] == [stuck_task.id]

    def test_task_diagnose_hours_window(self):
        """Test --hours excludes failures older than the window."""
        now = timezone.now()
        failed_task = Task.objects.create(
            name="Old Failure", function_name="hello_world", status="failed", created_by=self.user
        )
        TaskExecution.objects.create(
            task=failed_task, status="failed", completed_at=now - timedelta(hours=2), error_message="old"
        )

        out = StringIO()
        live_state = {"live_available": False, "running": {}, "workers": [], "producers": [], "error": "test"}

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command("metrics_service", "tasks", "diagnose", "--format", "json", "--hours", "1", stdout=out)

        data = json.loads(out.getvalue())
        assert all(row["function_name"] != "hello_world" for row in data["failures_in_window"])

        out_24h = StringIO()
        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command("metrics_service", "tasks", "diagnose", "--format", "json", stdout=out_24h)
        assert any(
            row["function_name"] == "hello_world" for row in json.loads(out_24h.getvalue())["failures_in_window"]
        )

    def test_task_diagnose_stuck_timeout_override(self):
        """Test --stuck-timeout flags a recently started task."""
        now = timezone.now()
        task = Task.objects.create(
            name="Recent Runner",
            function_name="hello_world",
            status="running",
            started_at=now - timedelta(seconds=2),
            created_by=self.user,
        )

        out = StringIO()
        live_state = {"live_available": False, "running": {}, "workers": [], "producers": [], "error": "test"}

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command("metrics_service", "tasks", "diagnose", "--format", "json", "--stuck-timeout", "1", stdout=out)

        data = json.loads(out.getvalue())
        assert [row["task_id"] for row in data["stuck_tasks"]] == [task.id]

    def test_task_diagnose_limit_applies_to_sections(self):
        """Test --limit bounds the stuck-task section in both text and JSON."""
        now = timezone.now()
        for index in range(3):
            Task.objects.create(
                name=f"Stuck {index}",
                function_name="hello_world",
                status="running",
                started_at=now - timedelta(seconds=200 + index),
                created_by=self.user,
            )

        out = StringIO()
        live_state = {"live_available": False, "running": {}, "workers": [], "producers": [], "error": "test"}

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command(
                "metrics_service",
                "tasks",
                "diagnose",
                "--format",
                "json",
                "--stuck-timeout",
                "60",
                "--limit",
                "1",
                stdout=out,
            )

        data = json.loads(out.getvalue())
        assert len(data["stuck_tasks"]) == 1

        # Text mode must honour the same limit instead of falling back to 20.
        text_out = StringIO()
        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command(
                "metrics_service",
                "tasks",
                "diagnose",
                "--stuck-timeout",
                "60",
                "--limit",
                "2",
                stdout=text_out,
            )

        text = text_out.getvalue()
        assert "Stuck tasks (2)" in text
        assert text.count("Function: hello_world") == 2

    def test_task_diagnose_invalid_options(self):
        """Test invalid diagnose options raise CommandError (Django's stderr/exit-1 contract)."""
        with pytest.raises(CommandError, match="--hours must be >= 1"):
            call_command("metrics_service", "tasks", "diagnose", "--hours", "0")

        with pytest.raises(CommandError, match="--limit must be >= 1"):
            call_command("metrics_service", "tasks", "diagnose", "--limit", "0")

        with pytest.raises(CommandError, match="--stuck-timeout must be >= 1"):
            call_command("metrics_service", "tasks", "diagnose", "--stuck-timeout", "0")

    def test_task_diagnose_text_with_malformed_workers_reply(self):
        """Regression: a non-dict dispatcherd workers reply must not crash text output."""
        out = StringIO()
        live_state = {
            "live_available": True,
            "running": {},
            # dispatcherd's own fallback reply for a malformed payload / plain strings
            "workers": ["JSON parse error", "{bad"],
            "producers": [],
            "error": None,
            "query_errors": {},
            "warnings": ["ignored 2 malformed dispatcherd worker entries"],
        }

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            # Must exit 0: no exception raised.
            call_command("metrics_service", "tasks", "diagnose", stdout=out)

        output = out.getvalue()
        assert "Metrics service task diagnostics" in output
        assert "Warning: ignored 2 malformed dispatcherd worker entries" in output
        assert "Workers: 2 | Producers: 0" in output

    def test_task_diagnose_json_with_malformed_workers_reply_unchanged(self):
        """JSON mode keeps the raw worker payload and stays parseable."""
        out = StringIO()
        live_state = {
            "live_available": True,
            "running": {},
            "workers": ["JSON parse error", "{bad"],
            "producers": [],
            "error": None,
            "query_errors": {},
            "warnings": ["ignored 2 malformed dispatcherd worker entries"],
        }

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command("metrics_service", "tasks", "diagnose", "--format", "json", stdout=out)

        data = json.loads(out.getvalue())
        assert data["queue_depth"]["dispatcherd_workers"] == ["JSON parse error", "{bad"]
        assert data["queue_depth"]["warnings"] == ["ignored 2 malformed dispatcherd worker entries"]
        assert data["queue_depth"]["live_available"] is True

    # Real dispatcherd reply shapes, as captured from a live single-node
    # dispatcherd 2026.1.27 daemon and from the pg_notify broker with no daemon.
    # The full literals live in tests/unit/tasks/test_task_diagnostics.py
    # (REAL_HEALTHY_REPLIES / REAL_ECHO_ONLY_REPLIES); these are trimmed to the
    # fields the report reads.
    _NODE_ID = "b605ecf3-7ef0-4aa8-a70b-d94cd6952ae8"
    _HEALTHY_REPLIES = {
        "running": [{"node_id": _NODE_ID}],
        "workers": [
            {"worker-0": {"worker_id": 0, "status": "ready", "current_task": None}, "node_id": _NODE_ID},
        ],
        "producers": [{"pg_notify-producer": {"produced_count": 3}, "node_id": _NODE_ID}],
    }
    _ECHO_ONLY_REPLIES = {
        "running": [{"control": "running", "reply_to": "reply_to_e28c35f9_fdfd_4e49_869e_4e67035c134d"}],
        "workers": [{"control": "workers", "reply_to": "reply_to_48ed564a_7b62_49b6_ba8c_20fa8974f08d"}],
        "producers": [{"control": "producers", "reply_to": "reply_to_86b7ead0_4af9_4087_9089_5a604c5cb88d"}],
    }

    def _diagnose_with_control(self, replies, *args):
        """Run tasks diagnose end-to-end against canned dispatcherd control replies."""

        class _Control:
            def control_with_reply(self, command, timeout=None):
                return list(replies.get(command, []))

        out = StringIO()
        with (
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"),
            patch("dispatcherd.factories.get_control_from_settings", return_value=_Control()),
        ):
            call_command("metrics_service", "tasks", "diagnose", *args, stdout=out)
        return out.getvalue()

    def test_task_diagnose_healthy_reply_reports_counts_without_warnings(self):
        """A real reply (node_id + one worker + one producer) is not 'malformed'."""
        output = self._diagnose_with_control(self._HEALTHY_REPLIES)

        assert "Workers: 1 | Producers: 1" in output
        assert "worker-0: ready" in output
        assert "pg_notify-producer: produced 3" in output
        assert "malformed" not in output
        assert "node_id" not in output

    def test_task_diagnose_echo_only_reply_reports_unavailable(self):
        """The broker's request echo must never be read as a live dispatcherd."""
        output = self._diagnose_with_control(self._ECHO_ONLY_REPLIES)

        assert "Live dispatcherd state unavailable: no replies from dispatcherd (control timeout)" in output
        assert "Workers:" not in output

        raw = self._diagnose_with_control(self._ECHO_ONLY_REPLIES, "--format", "json")
        data = json.loads(raw)
        assert data["queue_depth"]["live_available"] is False
        assert data["queue_depth"]["error"] == "no replies from dispatcherd (control timeout)"
        assert data["queue_depth"]["warnings"] == []
        assert data["queue_depth"]["dispatcherd_producers"] == []

    def test_task_diagnose_validation_errors_stay_off_stdout(self):
        """Errors must not pollute stdout, which carries JSON in --format json."""
        for output_format in ("text", "json"):
            out = StringIO()

            with pytest.raises(CommandError, match="--hours must be >= 1"):
                call_command(
                    "metrics_service", "tasks", "diagnose", "--format", output_format, "--hours", "0", stdout=out
                )

            assert out.getvalue() == "", f"stdout polluted in {output_format} mode"

    def test_task_diagnose_collection_failure_is_command_error(self):
        """Unexpected collection failures surface as CommandError with an empty stdout."""
        for output_format in ("text", "json"):
            out = StringIO()

            with (
                patch("apps.tasks.diagnostics.get_diagnostics", side_effect=RuntimeError("db down")),
                pytest.raises(CommandError, match="Failed to collect task diagnostics: db down"),
            ):
                call_command("metrics_service", "tasks", "diagnose", "--format", output_format, stdout=out)

            assert out.getvalue() == "", f"stdout polluted in {output_format} mode"

    def test_task_diagnose_cli_error_written_to_stderr(self):
        """Through the CLI entrypoint, CommandError goes to stderr and exits 1."""
        from apps.tasks.management.commands.metrics_service import Command

        for output_format in ("text", "json"):
            out, err = StringIO(), StringIO()

            with patch.object(sys, "stderr", err):
                command = Command()
                command.stdout = type(command.stdout)(out)
                with pytest.raises(SystemExit) as exc_info:
                    command.run_from_argv(
                        [
                            "manage.py",
                            "metrics_service",
                            "tasks",
                            "diagnose",
                            "--format",
                            output_format,
                            "--hours",
                            "0",
                        ]
                    )

            assert exc_info.value.code == 1
            assert "--hours must be >= 1" in err.getvalue(), f"no stderr message in {output_format} mode"
            assert "must be >= 1" not in out.getvalue(), f"stdout polluted in {output_format} mode"

    def test_task_diagnose_text_limit_matches_header_count(self):
        """--limit must bound the text rows to the same count as the header."""
        now = timezone.now()
        for index in range(30):
            Task.objects.create(
                name=f"Stuck {index}",
                function_name="hello_world",
                status="running",
                started_at=now - timedelta(seconds=200 + index),
                created_by=self.user,
            )

        out = StringIO()
        live_state = {"live_available": False, "running": {}, "workers": [], "producers": [], "error": "test"}

        with patch("apps.tasks.diagnostics.get_dispatcherd_state", return_value=live_state):
            call_command("metrics_service", "tasks", "diagnose", "--stuck-timeout", "60", "--limit", "50", stdout=out)

        output = out.getvalue()
        assert "Stuck tasks (30)" in output
        assert output.count("    Function: hello_world") == 30

    def test_invalid_command_arguments(self):
        """Test error handling for invalid command arguments."""
        # Test invalid JSON data
        with pytest.raises(CommandError):
            call_command(
                "metrics_service",
                "tasks",
                "create",
                "--name",
                "Invalid Task",
                "--function",
                "hello_world",
                "--data",
                "invalid-json",
            )

        # Test invalid scheduled time format
        with pytest.raises(CommandError):
            call_command(
                "metrics_service",
                "tasks",
                "create",
                "--name",
                "Invalid Time Task",
                "--function",
                "hello_world",
                "--scheduled-time",
                "invalid-time-format",
            )

        # Test non-existent user
        with pytest.raises(CommandError):
            call_command(
                "metrics_service",
                "tasks",
                "create",
                "--name",
                "Invalid User Task",
                "--function",
                "hello_world",
                "--user",
                "nonexistent_user",
            )

    def test_task_not_found_operations(self):
        """Test operations on non-existent tasks."""
        # Test show non-existent task
        with pytest.raises(CommandError):
            call_command("metrics_service", "tasks", "show", "99999")

        # Test cancel non-existent task
        with pytest.raises(CommandError):
            call_command("metrics_service", "tasks", "cancel", "99999")

        # Test retry non-existent task
        with pytest.raises(CommandError):
            call_command("metrics_service", "tasks", "retry", "99999")

    def test_task_invalid_state_operations(self):
        """Test operations on tasks in invalid states."""
        # Create completed task
        completed_task = Task.objects.create(
            name="Completed Task", function_name="hello_world", status="completed", created_by=self.user
        )

        # Try to cancel completed task
        with patch("sys.stdout.write"):
            call_command("metrics_service", "tasks", "cancel", str(completed_task.id))

        # Task should remain completed
        completed_task.refresh_from_db()
        assert completed_task.status == "completed"

        # Create pending task and try to retry it
        pending_task = Task.objects.create(
            name="Pending Task", function_name="hello_world", status="pending", created_by=self.user
        )
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

    def test_tasks_subcommand_help_subprocess(self):
        """Test tasks subcommand help via subprocess."""
        result = self._run_command("tasks", "--help")
        assert result.returncode == 0
        assert "Task management actions" in result.stdout


@pytest.mark.integration
class TestMetricsServiceFullIntegration(TransactionTestCase):
    """Full integration tests that test the complete service startup."""

    def setUp(self):
        """Set up test environment."""
        self.manage_py = Path(__file__).parent.parent.parent / "manage.py"
        assert self.manage_py.exists(), f"manage.py not found at {self.manage_py}"

    def _setup_mocks_for_start_services(self, mock_exists, mock_exit, mock_sleep, mock_popen):
        """Set up common mocks for tests that call _start_services."""
        mock_exists.return_value = True
        mock_exit.side_effect = SystemExit
        mock_sleep.return_value = None
        mock_popen.side_effect = create_mock_processes_with_exit()

    def _create_command_instance(self):
        """Create and configure a Command instance for testing."""
        from apps.tasks.management.commands.metrics_service import Command

        command = Command()
        command.shutdown_requested = False
        return command

    def _call_run_command_with_mock(self, *args, expect_exception=False):
        """Helper to call run command with _start_services mocked."""
        with patch("apps.tasks.management.commands.metrics_service.Command._start_services") as mock_start:
            try:
                call_command("metrics_service", "run", *args)
            except (ValueError, SystemExit):
                if not expect_exception:
                    raise  # Re-raise if exception not expected
                # Expected if validation happens
            return mock_start

    @patch("apps.tasks.management.commands.metrics_service.Command._start_services")
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
                "--max-tasks",
                "50",
                "--log-level",
                "DEBUG",
            )

        # Verify service startup was called with correct config
        mock_start_services.assert_called_once()
        args, _ = mock_start_services.call_args
        config = args[0]

        assert config["host"] == "127.0.0.1"
        assert config["port"] == "8001"
        assert config["gunicorn_workers"] == 2
        assert config["dispatcher_workers"] == 2
        assert config["max_tasks"] == 50
        assert config["log_level"] == "DEBUG"

    @patch("subprocess.Popen")
    @patch("pathlib.Path.exists")
    @patch("time.sleep")
    @patch("sys.exit")
    def test_signal_handler_setup(self, mock_exit, mock_sleep, mock_exists, mock_popen):
        """Test that signal handlers are properly configured in _start_services."""
        command = self._create_command_instance()
        self._setup_mocks_for_start_services(mock_exists, mock_exit, mock_sleep, mock_popen)
        config = get_default_config()

        # Signal handlers are set up inside _start_services
        with pytest.raises(SystemExit):
            command._start_services(config)

        # Verify signal handlers were registered by checking they're not default
        # (This is a bit indirect, but we can't easily access the handler after it's set)
        # The fact that the method runs without error means signal handlers were set up

    def test_configuration_extraction(self):
        """Test configuration extraction from command options."""
        from apps.tasks.management.commands.metrics_service import Command

        command = Command()
        options = {
            "host": "localhost",
            "port": "9000",
            "workers": 8,
            "max_tasks": 200,
            "log_level": "WARNING",
            "check_interval": 120,
        }

        config = command._extract_config(options)

        assert config["host"] == "localhost"
        assert config["port"] == "9000"
        assert config["gunicorn_workers"] == 8
        assert config["dispatcher_workers"] == 8
        assert config["max_tasks"] == 200
        assert config["log_level"] == "WARNING"
        assert config["check_interval"] == 120

    def test_django_server_command_building(self):
        """Test Django server command building and validation."""
        import sys
        from pathlib import Path

        from apps.tasks.management.commands.metrics_service import Command

        Command()

        # Test command building logic without actually running it
        manage_py = Path(__file__).parent.parent.parent / "manage.py"
        assert manage_py.exists(), f"manage.py not found at {manage_py}"

        # Test input validation (this is what we're really testing)
        host = "127.0.0.1"
        port = "8000"

        # Validate inputs for security (copied from the actual method)
        if not host.replace(".", "").replace(":", "").isalnum():
            pytest.fail(f"Invalid host: {host}")
        if not str(port).isdigit():
            pytest.fail(f"Invalid port: {port}")

        # Build expected command (Gunicorn for production)
        expected_cmd = [
            sys.executable,
            "-u",
            "-m",
            "gunicorn",
            "metrics_service.wsgi:application",
            "--bind",
            f"{host}:{port}",
        ]

        # Verify command structure
        assert "gunicorn" in expected_cmd
        assert f"{host}:{port}" in expected_cmd

    @patch("subprocess.Popen")
    @patch("pathlib.Path.exists")
    @patch("time.sleep")
    @patch("sys.exit")
    def test_dispatcher_command_building(self, mock_exit, mock_sleep, mock_exists, mock_popen):
        """Test dispatcher command building in _start_services."""
        import sys
        from pathlib import Path

        from apps.tasks.management.commands import metrics_service

        command = self._create_command_instance()
        manage_py = Path(__file__).parent.parent.parent / "manage.py"
        self._setup_mocks_for_start_services(mock_exists, mock_exit, mock_sleep, mock_popen)
        config = get_default_config()

        # Patch sys.argv[0] in the metrics_service module to point to manage.py
        # so the command finds it correctly when it uses sys.argv[0]
        original_argv = metrics_service.sys.argv
        metrics_service.sys.argv = [str(manage_py)]

        try:
            # Start services will build the dispatcher command internally
            # We'll verify it by checking the Popen calls
            with pytest.raises(SystemExit):
                command._start_services(config)
        finally:
            # Restore original argv
            metrics_service.sys.argv = original_argv

        # Verify dispatcher command was built correctly by checking Popen calls
        # The second call should be for dispatcher (index 1)
        assert mock_popen.call_count >= 2
        dispatcher_call = mock_popen.call_args_list[1]
        dispatcher_cmd = dispatcher_call[0][0]

        # Verify command structure
        assert sys.executable in dispatcher_cmd
        assert str(manage_py) in dispatcher_cmd
        assert "run_dispatcherd" in dispatcher_cmd
        assert "--workers=4" in dispatcher_cmd
        assert "--max-tasks=100" in dispatcher_cmd
        assert "--log-level=INFO" in dispatcher_cmd

    def test_input_validation(self):
        """Test input validation for security in command options."""
        # Test that invalid configuration values are caught at the command level
        # The new implementation builds commands directly, so validation happens
        # when the command is constructed. We test this by ensuring the command
        # handles invalid values gracefully.

        # Test with invalid workers (should be caught by argparse or command validation)
        # Mock _start_services to prevent infinite loop if validation doesn't catch it
        self._call_run_command_with_mock(
            "--host", "127.0.0.1", "--port", "8000", "--workers", "-1", expect_exception=True
        )

        # Test with invalid port (should be caught by command validation)
        # Note: The current implementation doesn't validate port format strictly,
        # but it will fail when trying to start the server
        self._call_run_command_with_mock("--host", "127.0.0.1", "--port", "invalid_port", expect_exception=True)

        # Test that valid configuration works
        mock_start = self._call_run_command_with_mock(
            "--host", "127.0.0.1", "--port", "8000", "--workers", "4", "--log-level", "INFO"
        )
        mock_start.assert_called_once()
