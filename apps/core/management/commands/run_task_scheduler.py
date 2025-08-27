"""
Django management command to run the database task scheduler.
"""

import logging
import signal
import sys

from django.core.management.base import BaseCommand

from apps.core.tasks import TaskScheduler

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to run the database task scheduler."""

    help = "Run the database task scheduler to process scheduled tasks"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--poll-interval", type=int, default=30, help="How often to check for ready tasks (in seconds)"
        )
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level for scheduler",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        poll_interval = options["poll_interval"]
        log_level = options["log_level"]

        # Configure logging level
        scheduler_logger = logging.getLogger("apps.core.tasks")
        scheduler_logger.setLevel(getattr(logging, log_level))

        self.stdout.write(self.style.SUCCESS(f"Starting task scheduler with {poll_interval}s poll interval..."))

        # Create and start the scheduler
        scheduler = TaskScheduler(poll_interval=poll_interval)

        # Handle shutdown gracefully
        def signal_handler(signum, frame):
            self.stdout.write(self.style.WARNING("Received shutdown signal..."))
            scheduler.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            logger.info("Task scheduler started with configuration:")
            logger.info(f"  Poll interval: {poll_interval}s")
            logger.info(f"  Log level: {log_level}")

            # Start the scheduler (this will block)
            scheduler.start()

        except Exception as e:
            logger.error(f"Failed to start task scheduler: {str(e)}")
            self.stdout.write(self.style.ERROR(f"Start failed: {str(e)}"))
