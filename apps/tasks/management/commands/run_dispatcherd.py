"""
Django management command to run dispatcherd worker processes.

This command starts dispatcherd workers to process background tasks from the database.
"""

import sys

from django.core.management.base import BaseCommand

from apps.tasks.dispatcherd_config import setup_dispatcherd_config
from metrics_service.logger import get_logger

logger = get_logger(__name__)


class Command(BaseCommand):
    """Management command to run dispatcherd worker processes."""

    help = "Run dispatcherd worker processes for background task processing"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--workers",
            type=int,
            default=4,
            help="Number of worker processes (default: 4)",
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

    def handle(self, *args, **options):
        """Handle the command execution."""
        try:
            # Setup dispatcherd configuration
            setup_dispatcherd_config()

            # Import dispatcherd after configuration
            import dispatcherd

            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting dispatcherd with {options['workers']} workers "
                    f"(timeout: {options['timeout']}s, max_tasks: {options['max_tasks']})"
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
