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

            from apps.tasks.tasks import TASK_FUNCTIONS, TaskScheduler

            dispatcherd_logger = logging.getLogger("dispatcherd")
            dispatcherd_logger.setLevel(getattr(logging, log_level))

            logger.info("Dispatcherd started with configuration:")
            logger.info(f"  Workers: {workers}")
            logger.info(f"  Timeout: {timeout}s")
            logger.info(f"  Max tasks per worker: {max_tasks}")
            logger.info(f"  Log level: {log_level}")
            task_list = list(TASK_FUNCTIONS.keys())
            logger.info(f"  Available tasks: {task_list}")

            # Configure dispatcherd before running
            from django.conf import settings as django_settings

            # Build dispatcherd configuration from Django database settings
            db_config = django_settings.DATABASES["default"]

            # Create PostgreSQL connection config for dispatcherd
            pg_config = {
                "dbname": db_config["NAME"],
                "user": db_config["USER"],
                "password": db_config["PASSWORD"],
                "host": db_config["HOST"],
                "port": db_config["PORT"],
            }

            # Configure dispatcherd with pg_notify
            dispatcherd_config = {
                "version": 2,
                "brokers": {
                    "pg_notify": {
                        "config": pg_config,
                        "channels": [
                            "metrics_tasks",  # Main task channel
                            "metrics_cleanup",  # Cleanup tasks channel
                            "metrics_notifications",  # Notification tasks
                        ],
                    },
                },
                "service": {
                    "pool_kwargs": {"max_workers": workers},
                },
            }

            logger.info(
                f"Configuring dispatcherd with database: "
                f"{db_config['HOST']}:{db_config['PORT']}/{db_config['NAME']}"
            )
            dispatcherd.config.setup(dispatcherd_config)

            # Start task scheduler in a separate thread
            scheduler = TaskScheduler(poll_interval=5)
            scheduler_thread = threading.Thread(target=scheduler.start, daemon=True)
            scheduler_thread.start()
            self.stdout.write(self.style.SUCCESS("Task scheduler started in background"))

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
