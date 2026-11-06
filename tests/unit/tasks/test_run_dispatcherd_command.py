"""
Comprehensive unit tests for run_dispatcherd management command.

This module provides complete test coverage for the run_dispatcherd
management command including all execution paths and error handling.
"""

import builtins
import signal
import threading
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, override_settings

from apps.tasks.management.commands.run_dispatcherd import Command

# Captured before tests patch builtins.__import__, so the side effects below can
# fall back to the real importer instead of recursing into the patch.
_REAL_IMPORT = builtins.__import__


@pytest.mark.unit
class TestRunDispatcherdCommand(TestCase):
    """Test cases for run_dispatcherd management command."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.out = StringIO()
        self.err = StringIO()

    def _mock_dispatcherd_import(self, mock_dispatcherd):
        """Helper to create a proper dispatcherd import mock."""

        def import_side_effect(name, *args, **kwargs):
            if name == "dispatcherd":
                return mock_dispatcherd
            # Use the real __import__ for everything else
            return _REAL_IMPORT(name, *args, **kwargs)

        return import_side_effect

    def test_command_help_text(self):
        """Test that command has appropriate help text."""
        self.assertIsNotNone(self.command.help)
        self.assertIn("dispatcherd", self.command.help.lower())
        self.assertIn("worker", self.command.help.lower())

    def test_add_arguments_workers(self):
        """Test that workers argument is added correctly."""
        parser = MagicMock()
        self.command.add_arguments(parser)

        # Verify --workers argument was added
        calls = [c for c in parser.add_argument.call_args_list if "--workers" in c[0]]
        self.assertEqual(len(calls), 1)

        # Verify argument configuration
        call_kwargs = calls[0][1]
        self.assertEqual(call_kwargs["type"], int)
        self.assertEqual(call_kwargs["default"], 1)
        self.assertIn("worker", call_kwargs["help"].lower())

    def test_add_arguments_max_tasks(self):
        """Test that max-tasks argument is added correctly."""
        parser = MagicMock()
        self.command.add_arguments(parser)

        # Verify --max-tasks argument was added
        calls = [c for c in parser.add_argument.call_args_list if "--max-tasks" in c[0]]
        self.assertEqual(len(calls), 1)

        # Verify argument configuration
        call_kwargs = calls[0][1]
        self.assertEqual(call_kwargs["type"], int)
        self.assertEqual(call_kwargs["default"], 100)
        self.assertIn("maximum", call_kwargs["help"].lower())

    def test_add_arguments_log_level(self):
        """Test that log-level argument is added correctly."""
        parser = MagicMock()
        self.command.add_arguments(parser)

        # Verify --log-level argument was added
        calls = [c for c in parser.add_argument.call_args_list if "--log-level" in c[0]]
        self.assertEqual(len(calls), 1)

        # Verify argument configuration
        call_kwargs = calls[0][1]
        self.assertEqual(call_kwargs["choices"], ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.assertIsNone(call_kwargs["default"])
        self.assertIn("log level", call_kwargs["help"].lower())

    def test_add_arguments_all_args(self):
        """Test that all required arguments are added."""
        parser = MagicMock()
        self.command.add_arguments(parser)

        # Should have exactly 4 add_argument calls
        self.assertEqual(parser.add_argument.call_count, 4)

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_handle_default_options(self, mock_logging, mock_setup):
        """Test handle with default options."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        # Mock dispatcherd import
        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify the dispatcherd loggers were given the configured level
            mock_logging.getLogger.assert_any_call("dispatcherd")
            mock_logging.getLogger.return_value.setLevel.assert_called_with("INFO")

            # Verify dispatcherd setup was called
            mock_setup.assert_called_once()

            # Verify dispatcherd.run_service was called
            mock_dispatcherd.run_service.assert_called_once()

            # Verify success message
            output = self.out.getvalue()
            self.assertIn("Starting dispatcherd", output)
            self.assertIn("4 workers", output)
            self.assertIn("100", output)

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_handle_custom_workers(self, mock_logging, mock_setup):
        """Test handle with custom worker count."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 8,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            output = self.out.getvalue()
            self.assertIn("8 workers", output)

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_handle_custom_max_tasks(self, mock_logging, mock_setup):
        """Test handle with custom max_tasks."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 200,
            "log_level": "INFO",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            output = self.out.getvalue()
            self.assertIn("200", output)

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_handle_debug_log_level(self, mock_logging, mock_setup):
        """Test handle with DEBUG log level."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "DEBUG",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify DEBUG logging level was configured
            mock_logging.getLogger.return_value.setLevel.assert_called_with("DEBUG")

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_handle_defaults_log_level_to_settings(self, mock_logging, mock_setup):
        """ES-SUP-2: without --log-level the worker follows METRICS_SERVICE_LOG_LEVEL."""
        mock_dispatcherd = MagicMock()
        options = {"workers": 1, "timeout": 3600, "max_tasks": 100, "log_level": None}

        with (
            override_settings(LOG_LEVEL="warning"),
            patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)),
        ):
            self.command.stdout = self.out
            self.command.handle(**options)

        # Lowercase settings values must be normalised before reaching logging.
        mock_logging.getLogger.return_value.setLevel.assert_called_with("WARNING")

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_handle_warning_log_level(self, mock_logging, mock_setup):
        """Test handle with WARNING log level."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "WARNING",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify WARNING logging level was configured
            mock_logging.getLogger.return_value.setLevel.assert_called_with("WARNING")

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_handle_error_log_level(self, mock_logging, mock_setup):
        """Test handle with ERROR log level."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "ERROR",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify ERROR logging level was configured
            mock_logging.getLogger.return_value.setLevel.assert_called_with("ERROR")

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    @patch("sys.exit")
    def test_handle_import_error(self, mock_exit, mock_logging, mock_setup):
        """Test handle when dispatcherd import fails."""
        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        # Simulate ImportError by raising exception on import
        def import_side_effect(name, *args, **kwargs):
            if name == "dispatcherd":
                raise ImportError("Cannot import dispatcherd")
            return _REAL_IMPORT(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_side_effect):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify error message was written
            output = self.out.getvalue()
            self.assertIn("Failed to import dispatcherd", output)

            # Verify sys.exit(1) was called
            mock_exit.assert_called_once_with(1)

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    @patch("sys.exit")
    def test_handle_general_exception(self, mock_exit, mock_logging, mock_setup):
        """Test handle when general exception occurs."""
        mock_dispatcherd = MagicMock()
        mock_dispatcherd.run_service.side_effect = Exception("Test error")

        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify error message was written
            output = self.out.getvalue()
            self.assertIn("Failed to start dispatcherd", output)
            self.assertIn("Test error", output)

            # Verify sys.exit(1) was called
            mock_exit.assert_called_once_with(1)

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    @patch("sys.exit")
    def test_handle_setup_dispatcherd_exception(self, mock_exit, mock_logging, mock_setup):
        """Test handle when setup_dispatcherd_config raises exception."""
        mock_setup.side_effect = Exception("Setup failed")
        mock_dispatcherd = MagicMock()

        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify error message was written
            output = self.out.getvalue()
            self.assertIn("Failed to start dispatcherd", output)
            self.assertIn("Setup failed", output)

            # Verify sys.exit(1) was called
            mock_exit.assert_called_once_with(1)

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_handle_all_custom_options(self, mock_logging, mock_setup):
        """Test handle with all custom options."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 16,
            "timeout": 7200,
            "max_tasks": 500,
            "log_level": "DEBUG",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify all custom values in output
            output = self.out.getvalue()
            self.assertIn("16 workers", output)
            self.assertIn("500", output)

            # Verify DEBUG logging
            mock_logging.getLogger.return_value.setLevel.assert_called_with("DEBUG")

            # Verify setup and run were called
            mock_setup.assert_called_once()
            mock_dispatcherd.run_service.assert_called_once()

    def test_command_instance_attributes(self):
        """Test command instance has correct attributes."""
        self.assertTrue(hasattr(self.command, "help"))
        self.assertTrue(hasattr(self.command, "add_arguments"))
        self.assertTrue(hasattr(self.command, "handle"))

    def test_command_methods_callable(self):
        """Test that command methods are callable."""
        self.assertTrue(callable(self.command.add_arguments))
        self.assertTrue(callable(self.command.handle))

    def test_add_arguments_parser_type(self):
        """Test add_arguments accepts parser-like object."""
        parser = MagicMock()
        # Should not raise any exceptions
        self.command.add_arguments(parser)
        # Parser should have been used
        self.assertTrue(parser.add_argument.called)

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_logging_configuration_called_before_setup(self, mock_logging, mock_setup):
        """Test that logging is configured before dispatcherd setup."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        call_order = []

        def record_logging_call(*args, **kwargs):
            call_order.append("logging")

        def record_setup_call(*args, **kwargs):
            call_order.append("setup")

        mock_logging.getLogger.return_value.setLevel.side_effect = record_logging_call
        mock_setup.side_effect = record_setup_call

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify log levels were configured before setup
            self.assertEqual(call_order, ["logging", "logging", "setup"])

    @patch("apps.tasks.management.commands.run_dispatcherd.setup_dispatcherd_config")
    @patch("apps.tasks.management.commands.run_dispatcherd.logging")
    def test_dispatcherd_imported_after_setup(self, mock_logging, mock_setup):
        """Test that dispatcherd is imported after setup_dispatcherd_config."""
        mock_dispatcherd = MagicMock()
        options = {
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        with patch("builtins.__import__", side_effect=self._mock_dispatcherd_import(mock_dispatcherd)):
            self.command.stdout = self.out
            self.command.handle(**options)

            # Verify setup was called before dispatcherd.run_service
            mock_setup.assert_called_once()
            mock_dispatcherd.run_service.assert_called_once()

    def test_module_has_logger(self):
        """Test that module has logger configured."""
        from apps.tasks.management.commands.run_dispatcherd import logger

        self.assertIsNotNone(logger)
        self.assertEqual(logger.name, "apps.tasks.management.commands.run_dispatcherd")

    def test_module_imports(self):
        """Test that module has correct imports."""
        from apps.tasks.management.commands import run_dispatcherd

        self.assertTrue(hasattr(run_dispatcherd, "logging"))
        self.assertTrue(hasattr(run_dispatcherd, "sys"))
        self.assertTrue(hasattr(run_dispatcherd, "BaseCommand"))
        self.assertTrue(hasattr(run_dispatcherd, "setup_dispatcherd_config"))
        self.assertTrue(hasattr(run_dispatcherd, "logger"))
        self.assertTrue(hasattr(run_dispatcherd, "Command"))

    def test_command_class_docstring(self):
        """Test that Command class has docstring."""
        self.assertIsNotNone(Command.__doc__)
        self.assertIn("dispatcherd", Command.__doc__.lower())

    def test_add_arguments_docstring(self):
        """Test that add_arguments method has docstring."""
        self.assertIsNotNone(Command.add_arguments.__doc__)

    def test_handle_docstring(self):
        """Test that handle method has docstring."""
        self.assertIsNotNone(Command.handle.__doc__)


def _dispatcherd_import_side_effect(mock_dispatcherd):
    """Import dispatcherd from the mock and everything else for real."""

    def import_side_effect(name, *args, **kwargs):
        if name == "dispatcherd":
            return mock_dispatcherd
        return _REAL_IMPORT(name, *args, **kwargs)

    return import_side_effect


def _handle_options():
    return {"workers": 1, "timeout": 3600, "max_tasks": 100, "log_level": "INFO"}


@pytest.mark.unit
def test_handle_closes_db_connections_before_workers_fork():
    """The startup sync opens a connection; it must be closed before run_service forks.

    ``connections.close_all()`` is used rather than ``close_old_connections()``,
    which is a no-op when ``CONN_MAX_AGE > 0`` and would leave forked workers
    sharing the parent's socket.
    """
    command = Command()
    command.stdout = StringIO()

    with (
        patch("apps.core.logging_control.sync_dispatcherd_log_level"),
        patch("django.db.connections.close_all") as mock_close,
        patch("django.db.close_old_connections") as mock_close_old,
        patch("builtins.__import__", side_effect=_dispatcherd_import_side_effect(MagicMock())),
    ):
        command.handle(**_handle_options())

    mock_close.assert_called()
    mock_close_old.assert_not_called()


@pytest.mark.unit
def test_handle_closes_db_connections_when_startup_sync_fails():
    """A failed startup sync must not leave its connection behind for forked workers."""
    command = Command()
    command.stdout = StringIO()

    with (
        patch(
            "apps.core.logging_control.sync_dispatcherd_log_level",
            side_effect=RuntimeError("sync failed"),
        ),
        patch("django.db.connections.close_all") as mock_close,
        patch("builtins.__import__", side_effect=_dispatcherd_import_side_effect(MagicMock())),
    ):
        command.handle(**_handle_options())

    mock_close.assert_called()


# ---------------------------------------------------------------------------
# Fork model (AAP-79584): the refresh thread belongs to worker children only
# ---------------------------------------------------------------------------
@pytest.fixture
def log_level_thread():
    """Guarantee a clean, stopped refresh thread before and after a test."""
    from apps.core import logging_control

    logging_control.stop_refresh_thread()
    yield logging_control
    logging_control.stop_refresh_thread()


@pytest.fixture
def restore_signal_handlers():
    """Undo the signal handlers TaskWorker installs for its own process."""
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGUSR1)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


@pytest.mark.unit
def test_handle_does_not_start_refresh_thread_in_parent(log_level_thread):
    """The pre-fork parent must not have a DB-touching thread when it forks.

    This is the regression guard for the fork-safety risk: dispatcherd calls
    ``run_service()`` which forks the worker pool, so a thread started in
    ``handle()`` would be running (and possibly mid-query) at fork time. The old
    implementation started ``runtime-log-level-sync`` here; this test fails if
    that comes back.
    """
    command = Command()
    command.stdout = StringIO()

    with (
        patch("apps.core.logging_control.sync_dispatcherd_log_level"),
        patch("builtins.__import__", side_effect=_dispatcherd_import_side_effect(MagicMock())),
        patch(
            "apps.core.logging_control.start_refresh_thread",
            wraps=log_level_thread.start_refresh_thread,
        ) as mock_start,
    ):
        command.handle(**_handle_options())

    mock_start.assert_not_called()
    assert log_level_thread.active_refresh_thread() is None
    assert log_level_thread.REFRESH_THREAD_NAME not in [t.name for t in threading.enumerate()]


@pytest.mark.unit
def test_worker_child_starts_refresh_thread_after_fork(log_level_thread, restore_signal_handlers):
    """dispatcherd's post-fork hook starts the thread, and shutdown stops it.

    ``os.fork()`` is not reproducible inside pytest, so the fork boundary is
    modelled by calling ``on_start()`` directly: ``dispatcherd.worker.target.work_loop``
    calls nothing but ``worker.on_start()`` first in the child, after
    ``multiprocessing`` has forked it. Proves (a) the worker bootstraps the
    refresh thread, i.e. every child gets one, (b) it is a real live thread in
    this process, and (c) ``on_shutdown()`` leaves nothing behind. It does not
    prove the OS-level fork ordering; the parent-side assertion above covers
    the "nothing to inherit" half of that.
    """
    from apps.tasks.dispatcherd_worker import LogLevelSyncWorker

    worker = LogLevelSyncWorker(worker_id=0, message_queue=MagicMock(), finished_queue=MagicMock())
    assert log_level_thread.active_refresh_thread() is None, "premise: child starts without a thread"

    worker.on_start()
    thread = log_level_thread.active_refresh_thread()
    assert thread is not None
    assert thread.is_alive()
    assert thread.name == log_level_thread.REFRESH_THREAD_NAME
    assert thread.daemon is True

    # A second bootstrap must not create a second poller.
    worker.on_start()
    assert log_level_thread.active_refresh_thread() is thread

    worker.on_shutdown()
    assert log_level_thread.active_refresh_thread() is None


@pytest.mark.unit
def test_refresh_thread_loop_applies_log_level(log_level_thread, monkeypatch):
    """The thread polls the shared apply point, so an idle worker still updates."""
    applied = threading.Event()

    def fake_sync():
        applied.set()
        return "DEBUG"

    monkeypatch.setattr(log_level_thread, "sync_dispatcherd_log_level", fake_sync)
    monkeypatch.setattr(log_level_thread, "refresh_interval_seconds", lambda: 0.01)

    thread = log_level_thread.start_refresh_thread()
    assert thread is not None
    assert applied.wait(5.0), "the refresh loop never called sync_dispatcherd_log_level"
    assert thread.is_alive()

    log_level_thread.stop_refresh_thread()
    assert log_level_thread.active_refresh_thread() is None


@pytest.mark.unit
def test_stop_refresh_thread_is_safe_without_a_thread(log_level_thread):
    """Shutdown paths must be idempotent."""
    log_level_thread.stop_refresh_thread()
    log_level_thread.stop_refresh_thread()
    assert log_level_thread.active_refresh_thread() is None
