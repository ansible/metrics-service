"""
Django management command to run the task scheduler.

This command starts the task scheduler to handle cron-based recurring tasks.
"""

import logging
import sys
import time
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to run the task scheduler."""

    help = "Run the task scheduler for cron-based recurring tasks"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level (default: INFO)",
        )
        parser.add_argument(
            "--check-interval",
            type=int,
            default=60,
            help="Check interval in seconds (default: 60)",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        try:
            # Configure logging
            log_level = getattr(logging, options["log_level"])
            logging.basicConfig(level=log_level)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting task scheduler (check interval: {options['check_interval']}s)"
                )
            )
            
            # Import scheduler after Django setup
            from apps.tasks.cron_scheduler import get_scheduler, start_scheduler
            
            # Start the scheduler
            start_scheduler()
            scheduler = get_scheduler()
            
            self.stdout.write(self.style.SUCCESS("Task scheduler started successfully"))
            
            # Keep the scheduler running
            try:
                while True:
                    time.sleep(options["check_interval"])
                    if not scheduler.running:
                        self.stdout.write(self.style.ERROR("Scheduler stopped unexpectedly"))
                        break
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Received interrupt signal, stopping scheduler..."))
                from apps.tasks.cron_scheduler import stop_scheduler
                stop_scheduler()
                self.stdout.write(self.style.SUCCESS("Task scheduler stopped"))
            
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Failed to import scheduler: {e}"))
            sys.exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to start task scheduler: {e}"))
            sys.exit(1)