"""
Django management command to run dispatcherd worker processes.

This command starts dispatcherd workers to process background tasks from the database.
"""

import logging
import os
import sys
import threading

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tasks.dispatcherd_config import setup_dispatcherd_config

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to run dispatcherd worker processes."""

    help = "Run dispatcherd worker processes for background task processing"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Number of worker processes (default: 1)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=3600,
            help="Deprecated, no effect. Use METRICS_SERVICE_TASK_TIMEOUT env var.",
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
            help="Log level (default: INFO)",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        try:
            # Record this process's epoch before workers are forked so they
            # inherit it. A runtime log level override written before this
            # moment is treated as stale and ignored (AAP-79584).
            os.environ["METRICS_SERVICE_PROCESS_STARTED_AT"] = timezone.now().isoformat()

            log_level = getattr(logging, options["log_level"])
            logging.basicConfig(level=log_level)
            # Setup dispatcherd configuration
            setup_dispatcherd_config()

            # Apply any active runtime log level override for the dispatcherd
            # main process before it starts accepting work.
            try:
                from apps.core.logging_control import sync_dispatcherd_log_level

                sync_dispatcherd_log_level()
            except Exception as exc:
                logger.debug(f"Runtime log level sync skipped: {exc}")
            finally:
                # The sync query opens a database connection in this process.
                # Drop it before dispatcherd forks workers so they do not
                # inherit a socket shared with the parent, and so a failed
                # query cannot leave a broken connection behind.
                from django.db import close_old_connections, connection

                if not connection.in_atomic_block:
                    close_old_connections()

            # Import dispatcherd after configuration
            import dispatcherd

            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting dispatcherd with {options['workers']} workers (max_tasks: {options['max_tasks']})"
                )
            )

            # The main process has no request/task boundary, so reconcile the
            # runtime log level in the background; this is how clears and TTL
            # expiry reach the dispatcherd logger (AAP-79584).
            stop_event = threading.Event()
            sync_thread = threading.Thread(
                target=self._log_level_sync_loop,
                args=(stop_event,),
                name="runtime-log-level-sync",
                daemon=True,
            )
            sync_thread.start()

            # Start dispatcherd service
            try:
                dispatcherd.run_service()
            finally:
                stop_event.set()

        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Failed to import dispatcherd: {e}"))
            sys.exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to start dispatcherd: {e}"))
            sys.exit(1)

    @staticmethod
    def _log_level_sync_loop(stop_event: threading.Event) -> None:
        """Reconcile the runtime log level in the dispatcherd main process."""
        interval = float(getattr(settings, "RUNTIME_LOG_LEVEL_REFRESH_SECONDS", 1) or 1)
        interval = max(interval, 1.0)
        while not stop_event.wait(interval):
            try:
                # Imported in the loop so a failure (or a mocked import in
                # tests) is caught instead of killing the thread.
                from apps.core.logging_control import sync_dispatcherd_log_level

                sync_dispatcherd_log_level()
            except Exception as exc:  # noqa: BLE001 - never kill the sync loop
                logger.debug(f"Runtime log level sync skipped: {exc}")
