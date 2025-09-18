"""
Django management command to run the complete metrics service.

This command starts both the Django development server and the dispatcherd
worker in parallel, providing a single command to launch the complete
metrics service.
"""

import logging
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to run the complete metrics service.

    This command starts both the Django runserver and the run_dispatcherd
    commands in parallel, allowing the full service to be started with a
    single command.
    """

    help = "Run the complete metrics service (Django server + dispatcher)"

    def add_arguments(self, parser):
        """
        Add command line arguments.

        Args:
            parser: ArgumentParser instance to add arguments to
        """
        # Django runserver arguments
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Host to bind the Django server to (default: 127.0.0.1)",
        )
        parser.add_argument(
            "--port",
            default="8000",
            help="Port to bind the Django server to (default: 8000)",
        )
        # Dispatcher arguments
        parser.add_argument(
            "--workers",
            type=int,
            default=4,
            help="Number of dispatcher worker processes (default: 4)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=3600,
            help="Task timeout in seconds (default: 3600)",
        )
        parser.add_argument(
            "--max-tasks",
            type=int,
            default=100,
            help="Maximum tasks per worker before respawn (default: 100)",
        )
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level for both services (default: INFO)",
        )

    def handle(self, *args, **options):
        """
        Handle the command execution.

        This method starts both the Django development server and the
        dispatcher service in separate threads, then waits for shutdown
        signals.

        Args:
            *args: Positional arguments (unused)
            **options: Command options
        """
        config = self._extract_config(options)
        self._initialize_service_state()
        self._setup_signal_handlers()
        self._start_services(config)

    def _extract_config(self, options):
        """Extract configuration from command options."""
        return {
            "host": options["host"],
            "port": options["port"],
            "workers": options["workers"],
            "timeout": options["timeout"],
            "max_tasks": options["max_tasks"],
            "log_level": options["log_level"],
        }

    def _initialize_service_state(self):
        """Initialize shared state for service management."""
        self.shutdown_requested = False
        self.threads = []
        self.processes = []

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            """Handle shutdown signals gracefully."""
            self.stdout.write(self.style.WARNING("Received shutdown signal..."))
            self.shutdown_requested = True
            self._cleanup_processes_and_threads()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _cleanup_processes_and_threads(self):
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

    def _start_services(self, config):
        """Start Django server and dispatcher services."""
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting metrics service:\n"
                f"  Django server: http://{config['host']}:{config['port']}\n"
                f"  Dispatcher workers: {config['workers']}\n"
                f"  Log level: {config['log_level']}"
            )
        )

        try:
            self._start_django_thread(config)
            self._start_dispatcher_thread(config)
            self._monitor_services(config)
        except Exception as e:
            logger.error(f"Failed to start metrics service: {str(e)}")
            self.stdout.write(self.style.ERROR(f"Start failed: {str(e)}"))
            sys.exit(1)

    def _start_django_thread(self, config):
        """Start Django server in a separate thread."""
        runserver_thread = threading.Thread(
            target=self._run_django_server, args=(config["host"], config["port"], config["log_level"]), daemon=True
        )
        runserver_thread.start()
        self.threads.append(runserver_thread)

    def _start_dispatcher_thread(self, config):
        """Start dispatcher in a separate thread."""
        dispatcher_thread = threading.Thread(
            target=self._run_dispatcherd,
            args=(config["workers"], config["timeout"], config["max_tasks"], config["log_level"]),
            daemon=True,
        )
        dispatcher_thread.start()
        self.threads.append(dispatcher_thread)

    def _monitor_services(self, config):
        """Monitor running services and handle failures."""
        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Django server started on http://{config['host']}:{config['port']}\n"
                f"✓ Dispatcher started with {config['workers']} workers\n"
                f"✓ Metrics service is running. Press Ctrl+C to stop."
            )
        )

        runserver_thread, dispatcher_thread = self.threads[:2]

        # Keep the main thread alive
        while not self.shutdown_requested:
            time.sleep(1)

            # Check if threads are still alive
            if not runserver_thread.is_alive():
                self.stdout.write(self.style.ERROR("Django server thread stopped unexpectedly"))
                break

            if not dispatcher_thread.is_alive():
                self.stdout.write(self.style.ERROR("Dispatcher thread stopped unexpectedly"))
                break

    def _run_django_server(self, host, port, log_level):
        """
        Run the Django development server.

        Args:
            host: Host to bind to
            port: Port to bind to
            log_level: Logging level
        """
        try:
            # Configure Django logging
            django_logger = logging.getLogger("django")
            django_logger.setLevel(getattr(logging, log_level))

            # Use subprocess to run runserver to avoid conflicts
            manage_py = Path(__file__).parent.parent.parent.parent.parent / "manage.py"

            # Validate inputs for security
            if not manage_py.exists():
                raise ValueError(f"manage.py not found at {manage_py}")

            # Sanitize host and port inputs
            if not isinstance(host, str) or not host.replace(".", "").replace(":", "").isalnum():
                raise ValueError(f"Invalid host: {host}")
            if not isinstance(port, int | str) or not str(port).isdigit():
                raise ValueError(f"Invalid port: {port}")

            cmd = [
                sys.executable,
                str(manage_py),
                "runserver",
                f"{host}:{port}",
                "--noreload",  # Disable auto-reload to prevent conflicts
            ]

            if log_level == "DEBUG":
                cmd.append("--verbosity=2")

            self.stdout.write(f"Starting Django server: {' '.join(cmd)}")
            # nosec B603 - command constructed from validated inputs
            process = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )

            # Store process reference for cleanup
            self.processes.append(process)

            # Stream output
            while not self.shutdown_requested and process.poll() is None:
                line = process.stdout.readline()
                if line:
                    self.stdout.write(f"[Django] {line.strip()}")

            if process.poll() is None:
                process.terminate()
                process.wait()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Django server error: {str(e)}"))

    def _run_dispatcherd(self, workers, timeout, max_tasks, log_level):
        """
        Run the dispatcher service.

        Args:
            workers: Number of worker processes
            timeout: Task timeout in seconds
            max_tasks: Maximum tasks per worker
            log_level: Logging level
        """
        try:
            cmd = self._build_dispatcher_command(workers, timeout, max_tasks, log_level)
            process = self._start_dispatcher_process(cmd)
            if process:
                self._monitor_dispatcher_process(process)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Dispatcher error: {str(e)}"))

    def _build_dispatcher_command(self, workers, timeout, max_tasks, log_level):
        """Build and validate dispatcher command."""
        manage_py = Path(__file__).parent.parent.parent.parent.parent / "manage.py"

        # Validate inputs for security
        if not manage_py.exists():
            raise ValueError(f"manage.py not found at {manage_py}")

        # Validate parameters
        if not isinstance(workers, int) or workers <= 0:
            raise ValueError(f"Invalid workers count: {workers}")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"Invalid timeout: {timeout}")
        if not isinstance(max_tasks, int) or max_tasks <= 0:
            raise ValueError(f"Invalid max_tasks: {max_tasks}")
        if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            raise ValueError(f"Invalid log_level: {log_level}")

        return [
            sys.executable,
            str(manage_py),
            "run_dispatcherd",
            f"--workers={workers}",
            f"--timeout={timeout}",
            f"--max-tasks={max_tasks}",
            f"--log-level={log_level}",
        ]

    def _start_dispatcher_process(self, cmd):
        """Start the dispatcher process."""
        self.stdout.write(f"Starting dispatcher: {' '.join(cmd)}")
        try:
            # nosec B603 - command constructed from validated inputs
            process = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )
            self.processes.append(process)
            return process
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Dispatcher error: {str(e)}"))
            return None

    def _monitor_dispatcher_process(self, process):
        """Monitor dispatcher process output."""
        # Stream output
        while not self.shutdown_requested and process.poll() is None:
            line = process.stdout.readline()
            if line:
                self.stdout.write(f"[Dispatcher] {line.strip()}")

        if process.poll() is None:
            process.terminate()
            process.wait()
