"""
Django management command to run dispatcherd worker processes.

This command starts dispatcherd workers to process background tasks from the database.
"""

import logging
import os
import sys

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
                from apps.core.logging_control import sync_from_db

                sync_from_db(force=True)
            except Exception as exc:
                logger.debug(f"Runtime log level sync skipped: {exc}")

            # Import dispatcherd after configuration
            import dispatcherd

            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting dispatcherd with {options['workers']} workers (max_tasks: {options['max_tasks']})"
                )
            )

            # Start dispatcherd service
            dispatcherd.run_service()

        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Failed to import dispatcherd: {e}"))
            sys.exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to start dispatcherd: {e}"))
            sys.exit(1)
