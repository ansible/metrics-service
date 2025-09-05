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
from django.core.management import call_command

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to run the complete metrics service.

    This command starts both the Django runserver and the run_dispatcher
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
        host = options["host"]
        port = options["port"]
        workers = options["workers"]
        timeout = options["timeout"]
        max_tasks = options["max_tasks"]
        log_level = options["log_level"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting metrics service:\n"
                f"  Django server: http://{host}:{port}\n"
                f"  Dispatcher workers: {workers}\n"
                f"  Log level: {log_level}"
            )
        )

        # Shared state for graceful shutdown
        self.shutdown_requested = False
        self.threads = []
        self.processes = []

        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            """Handle shutdown signals gracefully."""
            self.stdout.write(self.style.WARNING("Received shutdown signal..."))
            self.shutdown_requested = True

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

            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            # Start Django runserver in a separate thread
            runserver_thread = threading.Thread(
                target=self._run_django_server, args=(host, port, log_level), daemon=True
            )
            runserver_thread.start()
            self.threads.append(runserver_thread)

            # Start dispatcher in a separate thread
            dispatcher_thread = threading.Thread(
                target=self._run_dispatcher, args=(workers, timeout, max_tasks, log_level), daemon=True
            )
            dispatcher_thread.start()
            self.threads.append(dispatcher_thread)

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Django server started on http://{host}:{port}\n"
                    f"✓ Dispatcher started with {workers} workers\n"
                    f"✓ Metrics service is running. Press Ctrl+C to stop."
                )
            )

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

        except Exception as e:
            logger.error(f"Failed to start metrics service: {str(e)}")
            self.stdout.write(self.style.ERROR(f"Start failed: {str(e)}"))
            sys.exit(1)

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
            process = subprocess.Popen(
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

    def _run_dispatcher(self, workers, timeout, max_tasks, log_level):
        """
        Run the dispatcher service.

        Args:
            workers: Number of worker processes
            timeout: Task timeout in seconds
            max_tasks: Maximum tasks per worker
            log_level: Logging level
        """
        try:
            # Use subprocess to run the dispatcher to avoid event loop conflicts
            manage_py = Path(__file__).parent.parent.parent.parent.parent / "manage.py"

            cmd = [
                sys.executable,
                str(manage_py),
                "run_dispatcher",
                f"--workers={workers}",
                f"--timeout={timeout}",
                f"--max-tasks={max_tasks}",
                f"--log-level={log_level}",
            ]

            self.stdout.write(f"Starting dispatcher: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )

            # Store process reference for cleanup
            self.processes.append(process)

            # Stream output
            while not self.shutdown_requested and process.poll() is None:
                line = process.stdout.readline()
                if line:
                    self.stdout.write(f"[Dispatcher] {line.strip()}")

            if process.poll() is None:
                process.terminate()
                process.wait()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Dispatcher error: {str(e)}"))
