"""
Django management command to run the database task scheduler.

This module provides a Django management command for running the task
scheduler daemon that processes scheduled tasks from the database.
"""

import logging
import signal
import sys

from django.core.management.base import BaseCommand

from apps.tasks.tasks import TaskScheduler

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to run the database task scheduler.

    This command starts a long-running task scheduler process that polls
    the database for ready tasks and submits them for execution. It supports
    graceful shutdown and configurable polling intervals.
    """

    help = "Run the database task scheduler to process scheduled tasks"

    def add_arguments(self, parser):
        """
        Add command line arguments for the scheduler.

        Args:
            parser: ArgumentParser instance to add arguments to

        Returns:
            None
        """
        parser.add_argument(
            "--poll-interval", type=int, default=30, help="How often to check for ready tasks (in seconds)"
        )
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level for scheduler output",
        )

    def handle(self, *args, **options):
        """
        Handle the command execution.

        This method sets up the task scheduler with the specified configuration,
        configures signal handlers for graceful shutdown, and starts the
        scheduler process.

        Args:
            *args: Positional arguments (unused)
            **options: Command options including poll_interval and log_level

        Returns:
            None
        """
        poll_interval = options["poll_interval"]
        log_level = options["log_level"]

        # Configure logging level
        scheduler_logger = logging.getLogger("apps.tasks.tasks")
        scheduler_logger.setLevel(getattr(logging, log_level))

        self.stdout.write(self.style.SUCCESS(f"Starting task scheduler with {poll_interval}s poll interval..."))

        # Create and start the scheduler
        scheduler = TaskScheduler(poll_interval=poll_interval)

        # Handle shutdown gracefully
        def signal_handler(signum, frame):
            """
            Handle shutdown signals gracefully.

            Args:
                signum: Signal number
                frame: Current stack frame

            Returns:
                None
            """
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
