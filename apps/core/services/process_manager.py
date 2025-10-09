"""
Process management service.

Handles starting, monitoring, and managing subprocesses for the metrics service,
including Django server, dispatcher, and task scheduler.
"""

import logging
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from django.core.management.base import CommandError

logger = logging.getLogger(__name__)


class ProcessManager:
    """Manages subprocess lifecycle and monitoring for the metrics service."""

    def __init__(self, output_formatter):
        """
        Initialize the process manager.

        Args:
            output_formatter: OutputFormatter instance for consistent output
        """
        self.output = output_formatter
        self.shutdown_requested = False
        self.threads: list[threading.Thread] = []
        self.processes: list[subprocess.Popen] = []
        self._setup_signal_handlers()

    def start_services(self, config: dict[str, Any]) -> None:
        """
        Start all services (Django, dispatcher, task scheduler).

        Args:
            config: Configuration dictionary
        """
        self.output.success(
            f"Starting metrics service:\n"
            f"  Django server: http://{config['host']}:{config['port']}\n"
            f"  Dispatcher workers: {config['workers']}\n"
            f"  Task scheduler: enabled\n"
            f"  Log level: {config['log_level']}"
        )

        try:
            self._start_django_thread(config)
            self._start_dispatcher_thread(config)
            self._start_task_scheduler_thread(config)

            # Process any pending database tasks on startup
            self._process_pending_tasks_on_startup()

            self._monitor_services(config)
        except Exception as e:
            logger.error(f"Failed to start metrics service: {str(e)}")
            self.output.error(f"Start failed: {str(e)}")
            raise CommandError(f"Failed to start services: {e}") from e

    def _start_django_thread(self, config: dict[str, Any]) -> None:
        """Start Django server in a separate thread."""
        runserver_thread = threading.Thread(
            target=self._run_django_server, args=(config["host"], config["port"], config["log_level"]), daemon=True
        )
        runserver_thread.start()
        self.threads.append(runserver_thread)

    def _start_dispatcher_thread(self, config: dict[str, Any]) -> None:
        """Start dispatcher in a separate thread."""
        dispatcher_thread = threading.Thread(
            target=self._run_dispatcherd,
            args=(config["workers"], config["timeout"], config["max_tasks"], config["log_level"]),
            daemon=True,
        )
        dispatcher_thread.start()
        self.threads.append(dispatcher_thread)

    def _start_task_scheduler_thread(self, config: dict[str, Any]) -> None:
        """Start task scheduler in a separate thread."""
        task_scheduler_thread = threading.Thread(
            target=self._run_task_scheduler,
            args=(config["log_level"],),
            daemon=True,
        )
        task_scheduler_thread.start()
        self.threads.append(task_scheduler_thread)

    def _monitor_services(self, config: dict[str, Any]) -> None:
        """Monitor running services and handle failures."""
        self.output.success(
            f"✓ Django server started on http://{config['host']}:{config['port']}\n"
            f"✓ Dispatcher started with {config['workers']} workers\n"
            f"✓ Task scheduler started\n"
            f"✓ Metrics service is running. Press Ctrl+C to stop."
        )

        if len(self.threads) < 3:
            raise CommandError("Not all service threads started successfully")

        runserver_thread, dispatcher_thread, task_scheduler_thread = self.threads[:3]

        # Keep the main thread alive
        while not self.shutdown_requested:
            time.sleep(1)

            # Check if threads are still alive
            if not runserver_thread.is_alive():
                self.output.error("Django server thread stopped unexpectedly")
                break

            if not dispatcher_thread.is_alive():
                self.output.error("Dispatcher thread stopped unexpectedly")
                break

            if not task_scheduler_thread.is_alive():
                self.output.error("Task scheduler thread stopped unexpectedly")
                break

    def _process_pending_tasks_on_startup(self) -> None:
        """Process any pending database tasks on startup."""
        try:
            # Give dispatcherd a moment to start up
            time.sleep(2)

            from apps.tasks.models import Task
            from apps.tasks.tasks import submit_task_to_dispatcher

            # Get pending tasks that are ready to run
            pending_tasks = Task.objects.filter(status="pending").order_by("created")[:10]

            if not pending_tasks:
                self.output.write("📋 No pending tasks to process")
                return

            self.output.write(f"📋 Processing {len(pending_tasks)} pending tasks...")

            processed = 0
            for task in pending_tasks:
                if task.is_ready_to_run():
                    try:
                        submit_task_to_dispatcher(task)
                        self.output.write(f"  ✅ Submitted: {task.name}")
                        processed += 1
                    except Exception as e:
                        self.output.write(f"  ❌ Failed: {task.name} - {e}")
                else:
                    self.output.write(f"  ⏭️  Skipped: {task.name} (not ready)")

            if processed > 0:
                self.output.success(f"📋 Processed {processed} pending tasks")

        except Exception as e:
            self.output.warning(f"⚠️  Failed to process pending tasks: {e}")

    def _run_django_server(self, host: str, port: str, log_level: str) -> None:
        """Run the Django development server."""
        try:
            # Configure Django logging
            django_logger = logging.getLogger("django")
            django_logger.setLevel(getattr(logging, log_level))

            # Use subprocess to run runserver to avoid conflicts
            manage_py = self._get_manage_py_path()
            cmd = self._build_django_command(manage_py, host, port, log_level)

            self.output.write(f"Starting Django server: {' '.join(cmd)}")
            process = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )

            self.processes.append(process)
            self._monitor_process_output(process, "[Django]")

        except Exception as e:
            self.output.error(f"Django server error: {str(e)}")

    def _run_dispatcherd(self, workers: int, timeout: int, max_tasks: int, log_level: str) -> None:
        """Run the dispatcher service with proper configuration."""
        try:
            # Ensure dispatcherd config is set up before starting
            self._setup_dispatcherd_config()

            cmd = self._build_dispatcher_command(workers, timeout, max_tasks, log_level)
            process = self._start_process(cmd, "dispatcher")
            if process:
                self._monitor_process_output(process, "[Dispatcher]")
        except Exception as e:
            self.output.error(f"Dispatcher error: {str(e)}")

    def _run_task_scheduler(self, log_level: str) -> None:
        """Run the task scheduler service."""
        try:
            cmd = self._build_task_scheduler_command(log_level)
            process = self._start_process(cmd, "task scheduler")
            if process:
                self._monitor_process_output(process, "[TaskScheduler]")
        except Exception as e:
            self.output.error(f"Task scheduler error: {str(e)}")

    def _get_manage_py_path(self) -> Path:
        """Get the path to manage.py."""
        manage_py = Path(__file__).parent.parent.parent.parent / "manage.py"
        if not manage_py.exists():
            raise ValueError(f"manage.py not found at {manage_py}")
        return manage_py

    def _build_django_command(self, manage_py: Path, host: str, port: str, log_level: str) -> list[str]:
        """Build Django runserver command."""
        self._validate_host_port(host, port)

        cmd = [
            sys.executable,
            str(manage_py),
            "runserver",
            f"{host}:{port}",
            "--noreload",  # Disable auto-reload to prevent conflicts
        ]

        if log_level == "DEBUG":
            cmd.append("--verbosity=2")

        return cmd

    def _build_dispatcher_command(self, workers: int, timeout: int, max_tasks: int, log_level: str) -> list[str]:
        """Build dispatcher command."""
        manage_py = self._get_manage_py_path()
        self._validate_dispatcher_params(workers, timeout, max_tasks, log_level)

        return [
            sys.executable,
            str(manage_py),
            "run_dispatcherd",
            f"--workers={workers}",
            f"--timeout={timeout}",
            f"--max-tasks={max_tasks}",
            f"--log-level={log_level}",
        ]

    def _build_task_scheduler_command(self, log_level: str) -> list[str]:
        """Build task scheduler command."""
        manage_py = self._get_manage_py_path()
        self._validate_log_level(log_level)

        return [
            sys.executable,
            str(manage_py),
            "run_task_scheduler",
            f"--log-level={log_level}",
        ]

    def _start_process(self, cmd: list[str], name: str) -> subprocess.Popen | None:
        """Start a subprocess."""
        self.output.write(f"Starting {name}: {' '.join(cmd)}")
        try:
            process = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )
            self.processes.append(process)
            return process
        except Exception as e:
            self.output.error(f"{name} error: {str(e)}")
            return None

    def _monitor_process_output(self, process: subprocess.Popen, prefix: str) -> None:
        """Monitor process output."""
        while not self.shutdown_requested and process.poll() is None:
            line = process.stdout.readline()
            if line:
                self.output.write(f"{prefix} {line.strip()}")

        if process.poll() is None:
            process.terminate()
            process.wait()

    def _validate_host_port(self, host: str, port: str) -> None:
        """Validate host and port parameters."""
        if not isinstance(host, str) or not host:
            raise ValueError(f"Invalid host: {host}")
        if not isinstance(port, int | str) or not str(port).isdigit():
            raise ValueError(f"Invalid port: {port}")

    def _validate_dispatcher_params(self, workers: int, timeout: int, max_tasks: int, log_level: str) -> None:
        """Validate dispatcher parameters."""
        if not isinstance(workers, int) or workers <= 0:
            raise ValueError(f"Invalid workers count: {workers}")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"Invalid timeout: {timeout}")
        if not isinstance(max_tasks, int) or max_tasks <= 0:
            raise ValueError(f"Invalid max_tasks: {max_tasks}")
        self._validate_log_level(log_level)

    def _validate_log_level(self, log_level: str) -> None:
        """Validate log level."""
        if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            raise ValueError(f"Invalid log_level: {log_level}")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            """Handle shutdown signals gracefully."""
            self.output.warning("Received shutdown signal...")
            self.shutdown_requested = True
            self._cleanup_processes_and_threads()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _setup_dispatcherd_config(self) -> None:
        """Setup dispatcherd configuration to match standalone command."""
        try:
            from apps.tasks.dispatcherd_config import setup_dispatcherd_config

            setup_dispatcherd_config()
            self.output.write("✓ Dispatcherd configuration initialized")
        except Exception as e:
            self.output.warning(f"⚠️  Failed to setup dispatcherd config: {e}")

    def _cleanup_processes_and_threads(self) -> None:
        """Clean up processes and threads during shutdown."""
        # Terminate processes
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

        # Wait for threads to finish
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=5)
