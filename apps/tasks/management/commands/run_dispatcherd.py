"""
Django management command to run dispatcherd worker.
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to run dispatcherd worker."""

    help = "Run dispatcherd background task worker"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument("--workers", type=int, default=4, help="Number of worker processes to spawn")
        parser.add_argument("--timeout", type=int, default=3600, help="Task timeout in seconds")
        parser.add_argument(
            "--max-tasks",
            type=int,
            default=100,
            help="Maximum tasks per worker before respawn",
        )
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level for dispatcher",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""

        workers = options["workers"]
        timeout = options["timeout"]
        max_tasks = options["max_tasks"]
        log_level = options["log_level"]

        self.stdout.write(self.style.SUCCESS(f"Starting dispatcherd with {workers} workers..."))

        try:
            # Import and configure dispatcherd
            # Configure logging level
            import logging
            import threading

            import dispatcherd
            import dispatcherd.config

            from apps.tasks.cron_scheduler import start_scheduler
            from apps.tasks.tasks import TASK_FUNCTIONS

            dispatcherd_logger = logging.getLogger("dispatcherd")
            dispatcherd_logger.setLevel(getattr(logging, log_level))

            logger.info("Dispatcherd started with configuration:")
            logger.info(f"  Workers: {workers}")
            logger.info(f"  Timeout: {timeout}s")
            logger.info(f"  Max tasks per worker: {max_tasks}")
            logger.info(f"  Log level: {log_level}")
            task_list = list(TASK_FUNCTIONS.keys())
            logger.info(f"  Available tasks: {task_list}")

            # Configure dispatcherd using shared configuration
            from apps.tasks.dispatcherd_config import setup_dispatcherd_config

            logger.info("Setting up dispatcherd configuration...")
            setup_dispatcherd_config()

            # Start cron-based task scheduler
            cron_scheduler = start_scheduler()
            self.stdout.write(self.style.SUCCESS("Cron-based task scheduler started"))

            # Start dispatcherd service
            self.stdout.write(self.style.SUCCESS("Starting dispatcherd service..."))

            # This will start the dispatcher and block until stopped
            dispatcherd.run_service()

        except ImportError as e:
            logger.error(f"Failed to import dispatcherd: {str(e)}")
            self.stdout.write(self.style.ERROR(f"Import failed: {str(e)}"))
        except Exception as e:
            logger.error(f"Failed to start dispatcherd: {str(e)}")
            self.stdout.write(self.style.ERROR(f"Start failed: {str(e)}"))
