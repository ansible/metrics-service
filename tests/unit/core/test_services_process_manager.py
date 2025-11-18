"""
Unit tests for process manager service.
"""

import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.management.base import CommandError
from django.test import TestCase

from apps.core.services.process_manager import ProcessManager


class ProcessManagerTestCase(TestCase):
    """Test cases for ProcessManager."""

    def setUp(self):
        """Set up test data."""
        self.mock_output = Mock()
        self.process_manager = ProcessManager(self.mock_output)
        self.config = {
            "host": "127.0.0.1",
            "port": 8000,
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

    def test_init(self):
        """Test ProcessManager initialization."""
        self.assertEqual(self.process_manager.output, self.mock_output)
        self.assertFalse(self.process_manager.shutdown_requested)
        self.assertEqual(self.process_manager.threads, [])
        self.assertEqual(self.process_manager.processes, [])

    @patch("apps.core.services.process_manager.ProcessManager._setup_signal_handlers")
    def test_init_calls_signal_setup(self, mock_setup_signals):
        """Test initialization calls signal handlers setup."""
        ProcessManager(self.mock_output)
        mock_setup_signals.assert_called_once()

    @patch("apps.core.services.process_manager.ProcessManager._monitor_services")
    @patch("apps.core.services.process_manager.ProcessManager._process_pending_tasks_on_startup")
    @patch("apps.core.services.process_manager.ProcessManager._start_task_scheduler_thread")
    @patch("apps.core.services.process_manager.ProcessManager._start_dispatcher_thread")
    @patch("apps.core.services.process_manager.ProcessManager._start_django_thread")
    def test_start_services_success(self, mock_django, mock_dispatcher, mock_scheduler, mock_pending, mock_monitor):
        """Test successful service startup."""
        self.process_manager.start_services(self.config)

        # Verify all services were started
        mock_django.assert_called_once_with(self.config)
        mock_dispatcher.assert_called_once_with(self.config)
        mock_scheduler.assert_called_once_with(self.config)
        mock_pending.assert_called_once()
        mock_monitor.assert_called_once_with(self.config)

        # Verify output messages
        self.mock_output.success.assert_called()

    @patch("apps.core.services.process_manager.ProcessManager._start_django_thread")
    def test_start_services_failure(self, mock_django):
        """Test service startup failure handling."""
        mock_django.side_effect = Exception("Start failed")

        with self.assertRaises(CommandError) as cm:
            self.process_manager.start_services(self.config)

        self.assertIn("Failed to start services", str(cm.exception))
        self.mock_output.error.assert_called()

    @patch("threading.Thread")
    def test_start_django_thread(self, mock_thread):
        """Test Django thread startup."""
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        self.process_manager._start_django_thread(self.config)

        mock_thread.assert_called_once_with(
            target=self.process_manager._run_django_server, args=("127.0.0.1", 8000, "INFO"), daemon=True
        )
        mock_thread_instance.start.assert_called_once()
        self.assertIn(mock_thread_instance, self.process_manager.threads)

    @patch("threading.Thread")
    def test_start_dispatcher_thread(self, mock_thread):
        """Test dispatcher thread startup."""
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        self.process_manager._start_dispatcher_thread(self.config)

        mock_thread.assert_called_once_with(
            target=self.process_manager._run_dispatcherd, args=(4, 3600, 100, "INFO"), daemon=True
        )
        mock_thread_instance.start.assert_called_once()
        self.assertIn(mock_thread_instance, self.process_manager.threads)

    @patch("threading.Thread")
    def test_start_task_scheduler_thread(self, mock_thread):
        """Test task scheduler thread startup."""
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        self.process_manager._start_task_scheduler_thread(self.config)

        mock_thread.assert_called_once_with(
            target=self.process_manager._run_task_scheduler, args=("INFO",), daemon=True
        )
        mock_thread_instance.start.assert_called_once()
        self.assertIn(mock_thread_instance, self.process_manager.threads)

    def test_monitor_services_insufficient_threads(self):
        """Test monitor services with insufficient threads."""
        self.process_manager.threads = [Mock(), Mock()]  # Only 2 threads

        with self.assertRaises(CommandError) as cm:
            self.process_manager._monitor_services(self.config)

        self.assertIn("Not all service threads started successfully", str(cm.exception))

    @patch("time.sleep")
    def test_monitor_services_django_thread_dies(self, mock_sleep):
        """Test monitoring when Django thread dies."""
        mock_thread1 = Mock()
        mock_thread1.is_alive.return_value = False
        mock_thread2 = Mock()
        mock_thread2.is_alive.return_value = True
        mock_thread3 = Mock()
        mock_thread3.is_alive.return_value = True

        self.process_manager.threads = [mock_thread1, mock_thread2, mock_thread3]

        self.process_manager._monitor_services(self.config)

        self.mock_output.error.assert_called_with("Django server thread stopped unexpectedly")

    @patch("time.sleep")
    def test_monitor_services_dispatcher_thread_dies(self, mock_sleep):
        """Test monitoring when dispatcher thread dies."""
        mock_thread1 = Mock()
        mock_thread1.is_alive.return_value = True
        mock_thread2 = Mock()
        mock_thread2.is_alive.return_value = False
        mock_thread3 = Mock()
        mock_thread3.is_alive.return_value = True

        self.process_manager.threads = [mock_thread1, mock_thread2, mock_thread3]

        self.process_manager._monitor_services(self.config)

        self.mock_output.error.assert_called_with("Dispatcher thread stopped unexpectedly")

    @patch("time.sleep")
    def test_monitor_services_scheduler_thread_dies(self, mock_sleep):
        """Test monitoring when scheduler thread dies."""
        mock_thread1 = Mock()
        mock_thread1.is_alive.return_value = True
        mock_thread2 = Mock()
        mock_thread2.is_alive.return_value = True
        mock_thread3 = Mock()
        mock_thread3.is_alive.return_value = False

        self.process_manager.threads = [mock_thread1, mock_thread2, mock_thread3]

        self.process_manager._monitor_services(self.config)

        self.mock_output.error.assert_called_with("Task scheduler thread stopped unexpectedly")

    @patch("time.sleep")
    def test_monitor_services_shutdown_requested(self, mock_sleep):
        """Test monitoring with shutdown requested."""
        mock_thread1 = Mock()
        mock_thread1.is_alive.return_value = True
        mock_thread2 = Mock()
        mock_thread2.is_alive.return_value = True
        mock_thread3 = Mock()
        mock_thread3.is_alive.return_value = True

        self.process_manager.threads = [mock_thread1, mock_thread2, mock_thread3]
        self.process_manager.shutdown_requested = True

        self.process_manager._monitor_services(self.config)

        # Should exit without error messages
        self.mock_output.error.assert_not_called()

    @patch("apps.tasks.models.Task.objects.filter")
    @patch("time.sleep")
    def test_process_pending_tasks_general_error(self, mock_sleep, mock_filter):
        """Test processing pending tasks with general error."""
        mock_filter.side_effect = Exception("Database error")

        self.process_manager._process_pending_tasks_on_startup()

        self.mock_output.warning.assert_called_with("⚠️  Failed to process pending tasks: Database error")

    def test_get_manage_py_path_success(self):
        """Test getting manage.py path successfully."""
        with patch("pathlib.Path.exists", return_value=True):
            path = self.process_manager._get_manage_py_path()
            self.assertIsInstance(path, Path)
            self.assertTrue(str(path).endswith("manage.py"))

    def test_get_manage_py_path_not_found(self):
        """Test getting manage.py path when file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            with self.assertRaises(ValueError) as cm:
                self.process_manager._get_manage_py_path()
            self.assertIn("manage.py not found", str(cm.exception))

    @patch.object(ProcessManager, "_validate_host_port")
    @patch.object(ProcessManager, "_get_manage_py_path")
    def test_build_django_command(self, mock_get_path, mock_validate):
        """Test building Django command."""
        mock_path = Path("/fake/manage.py")
        mock_get_path.return_value = mock_path

        cmd = self.process_manager._build_django_command(mock_path, "127.0.0.1", "8000", "INFO")

        expected = [sys.executable, str(mock_path), "runserver", "127.0.0.1:8000", "--noreload"]
        self.assertEqual(cmd, expected)
        mock_validate.assert_called_once_with("127.0.0.1", "8000")

    @patch.object(ProcessManager, "_validate_host_port")
    @patch.object(ProcessManager, "_get_manage_py_path")
    def test_build_django_command_debug(self, mock_get_path, mock_validate):
        """Test building Django command with DEBUG log level."""
        mock_path = Path("/fake/manage.py")
        mock_get_path.return_value = mock_path

        cmd = self.process_manager._build_django_command(mock_path, "127.0.0.1", "8000", "DEBUG")

        self.assertIn("--verbosity=2", cmd)

    @patch.object(ProcessManager, "_validate_dispatcher_params")
    @patch.object(ProcessManager, "_get_manage_py_path")
    def test_build_dispatcher_command(self, mock_get_path, mock_validate):
        """Test building dispatcher command."""
        mock_path = Path("/fake/manage.py")
        mock_get_path.return_value = mock_path

        cmd = self.process_manager._build_dispatcher_command(4, 3600, 100, "INFO")

        expected = [
            sys.executable,
            str(mock_path),
            "run_dispatcherd",
            "--workers=4",
            "--timeout=3600",
            "--max-tasks=100",
        ]
        self.assertEqual(cmd, expected)
        mock_validate.assert_called_once_with(4, 3600, 100, "INFO")

    @patch.object(ProcessManager, "_validate_log_level")
    @patch.object(ProcessManager, "_get_manage_py_path")
    def test_build_task_scheduler_command(self, mock_get_path, mock_validate):
        """Test building task scheduler command."""
        mock_path = Path("/fake/manage.py")
        mock_get_path.return_value = mock_path

        cmd = self.process_manager._build_task_scheduler_command("INFO")

        expected = [sys.executable, str(mock_path), "run_task_scheduler"]
        self.assertEqual(cmd, expected)

    @patch("subprocess.Popen")
    def test_start_process_success(self, mock_popen):
        """Test starting process successfully."""
        mock_process = Mock()
        mock_popen.return_value = mock_process

        result = self.process_manager._start_process(["cmd", "arg"], "test-process")

        self.assertEqual(result, mock_process)
        self.assertIn(mock_process, self.process_manager.processes)
        self.mock_output.write.assert_called_with("Starting test-process: cmd arg")

    @patch("subprocess.Popen")
    def test_start_process_failure(self, mock_popen):
        """Test starting process failure."""
        mock_popen.side_effect = Exception("Process start failed")

        result = self.process_manager._start_process(["cmd", "arg"], "test-process")

        self.assertIsNone(result)
        self.mock_output.error.assert_called_with("test-process error: Process start failed")

    def test_validate_host_port_valid(self):
        """Test valid host and port validation."""
        # Should not raise exception
        self.process_manager._validate_host_port("127.0.0.1", "8000")
        self.process_manager._validate_host_port("localhost", 8000)

    def test_validate_host_port_invalid_host(self):
        """Test invalid host validation."""
        with self.assertRaises(ValueError) as cm:
            self.process_manager._validate_host_port("", "8000")
        self.assertIn("Invalid host", str(cm.exception))

        with self.assertRaises(ValueError):
            self.process_manager._validate_host_port(None, "8000")

    def test_validate_host_port_invalid_port(self):
        """Test invalid port validation."""
        with self.assertRaises(ValueError) as cm:
            self.process_manager._validate_host_port("127.0.0.1", "invalid")
        self.assertIn("Invalid port", str(cm.exception))

        with self.assertRaises(ValueError):
            self.process_manager._validate_host_port("127.0.0.1", "")

    @patch.object(ProcessManager, "_validate_log_level")
    def test_validate_dispatcher_params_valid(self, mock_validate_log):
        """Test valid dispatcher params validation."""
        # Should not raise exception
        self.process_manager._validate_dispatcher_params(4, 3600, 100, "INFO")
        mock_validate_log.assert_called_once_with("INFO")

    def test_validate_dispatcher_params_invalid_workers(self):
        """Test invalid workers validation."""
        with self.assertRaises(ValueError) as cm:
            self.process_manager._validate_dispatcher_params(0, 3600, 100, "INFO")
        self.assertIn("Invalid workers count", str(cm.exception))

        with self.assertRaises(ValueError):
            self.process_manager._validate_dispatcher_params(-1, 3600, 100, "INFO")

    def test_validate_dispatcher_params_invalid_timeout(self):
        """Test invalid timeout validation."""
        with self.assertRaises(ValueError) as cm:
            self.process_manager._validate_dispatcher_params(4, 0, 100, "INFO")
        self.assertIn("Invalid timeout", str(cm.exception))

    def test_validate_dispatcher_params_invalid_max_tasks(self):
        """Test invalid max_tasks validation."""
        with self.assertRaises(ValueError) as cm:
            self.process_manager._validate_dispatcher_params(4, 3600, 0, "INFO")
        self.assertIn("Invalid max_tasks", str(cm.exception))

    def test_validate_log_level_valid(self):
        """Test valid log level validation."""
        # Should not raise exceptions
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            self.process_manager._validate_log_level(level)

    def test_validate_log_level_invalid(self):
        """Test invalid log level validation."""
        with self.assertRaises(ValueError) as cm:
            self.process_manager._validate_log_level("INVALID")
        self.assertIn("Invalid log_level", str(cm.exception))

    @patch("signal.signal")
    def test_setup_signal_handlers(self, mock_signal):
        """Test signal handlers setup."""
        self.process_manager._setup_signal_handlers()

        # Verify signal handlers were set
        self.assertEqual(mock_signal.call_count, 2)
        calls = mock_signal.call_args_list
        self.assertEqual(calls[0][0][0], signal.SIGINT)
        self.assertEqual(calls[1][0][0], signal.SIGTERM)

    @patch.object(ProcessManager, "_cleanup_processes_and_threads")
    @patch("sys.exit")
    def test_signal_handler(self, mock_exit, mock_cleanup):
        """Test signal handler execution."""
        self.process_manager._setup_signal_handlers()

        # Get the signal handler function
        import signal

        with patch("signal.signal") as mock_signal:
            self.process_manager._setup_signal_handlers()
            signal_handler = mock_signal.call_args_list[0][0][1]

        # Call the signal handler
        signal_handler(signal.SIGINT, None)

        self.assertTrue(self.process_manager.shutdown_requested)
        mock_cleanup.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    def test_setup_dispatcherd_config_success(self, mock_setup):
        """Test successful dispatcherd config setup."""
        self.process_manager._setup_dispatcherd_config()

        mock_setup.assert_called_once()
        self.mock_output.write.assert_called_with("✓ Dispatcherd configuration initialized")

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    def test_setup_dispatcherd_config_failure(self, mock_setup):
        """Test dispatcherd config setup failure."""
        mock_setup.side_effect = Exception("Config failed")

        self.process_manager._setup_dispatcherd_config()

        self.mock_output.warning.assert_called_with("⚠️  Failed to setup dispatcherd config: Config failed")

    def test_cleanup_processes_and_threads(self):
        """Test cleanup of processes and threads."""
        # Create mock process
        mock_process = Mock()
        mock_process.poll.return_value = None  # Still running
        self.process_manager.processes = [mock_process]

        # Create mock thread
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        self.process_manager.threads = [mock_thread]

        self.process_manager._cleanup_processes_and_threads()

        # Verify process was terminated
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)

        # Verify thread was joined
        mock_thread.join.assert_called_once_with(timeout=5)

    def test_cleanup_processes_kill_on_timeout(self):
        """Test cleanup kills processes on timeout."""
        # Create mock process that times out
        mock_process = Mock()
        mock_process.poll.return_value = None  # Still running
        mock_process.wait.side_effect = subprocess.TimeoutExpired("cmd", 5)
        self.process_manager.processes = [mock_process]

        self.process_manager._cleanup_processes_and_threads()

        # Verify process was killed after timeout
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    @patch.object(ProcessManager, "_monitor_process_output")
    @patch.object(ProcessManager, "_build_django_command")
    @patch.object(ProcessManager, "_get_manage_py_path")
    @patch("subprocess.Popen")
    def test_run_django_server(self, mock_popen, mock_get_path, mock_build_cmd, mock_monitor):
        """Test running Django server."""
        mock_process = Mock()
        mock_popen.return_value = mock_process
        mock_path = Path("/fake/manage.py")
        mock_get_path.return_value = mock_path
        mock_build_cmd.return_value = ["python", "manage.py", "runserver"]

        self.process_manager._run_django_server("127.0.0.1", "8000", "INFO")
        mock_build_cmd.assert_called_once_with(mock_path, "127.0.0.1", "8000", "INFO")

        mock_popen.assert_called_once()
        self.assertIn(mock_process, self.process_manager.processes)
        mock_monitor.assert_called_once_with(mock_process, "[Django]")

    @patch.object(ProcessManager, "_monitor_process_output")
    @patch.object(ProcessManager, "_start_process")
    @patch.object(ProcessManager, "_build_dispatcher_command")
    @patch.object(ProcessManager, "_setup_dispatcherd_config")
    def test_run_dispatcherd(self, mock_setup, mock_build_cmd, mock_start, mock_monitor):
        """Test running dispatcher."""
        mock_process = Mock()
        mock_start.return_value = mock_process
        mock_build_cmd.return_value = ["python", "manage.py", "run_dispatcherd"]

        self.process_manager._run_dispatcherd(4, 3600, 100, "INFO")

        mock_setup.assert_called_once()
        mock_build_cmd.assert_called_once_with(4, 3600, 100, "INFO")
        mock_start.assert_called_once_with(["python", "manage.py", "run_dispatcherd"], "dispatcher")
        mock_monitor.assert_called_once_with(mock_process, "[Dispatcher]")

    @patch.object(ProcessManager, "_monitor_process_output")
    @patch.object(ProcessManager, "_start_process")
    @patch.object(ProcessManager, "_build_task_scheduler_command")
    def test_run_task_scheduler(self, mock_build_cmd, mock_start, mock_monitor):
        """Test running task scheduler."""
        mock_process = Mock()
        mock_start.return_value = mock_process
        mock_build_cmd.return_value = ["python", "manage.py", "run_task_scheduler"]

        self.process_manager._run_task_scheduler("INFO")

        mock_build_cmd.assert_called_once_with("INFO")
        mock_start.assert_called_once_with(["python", "manage.py", "run_task_scheduler"], "task scheduler")
        mock_monitor.assert_called_once_with(mock_process, "[TaskScheduler]")

    def test_monitor_process_output_shutdown_requested(self):
        """Test monitoring process output with shutdown requested."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Still running
        self.process_manager.shutdown_requested = True

        self.process_manager._monitor_process_output(mock_process, "[Test]")

        # Verify process was terminated
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()
