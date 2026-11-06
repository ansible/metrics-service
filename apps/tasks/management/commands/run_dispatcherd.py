"""
Django management command to run dispatcherd worker processes.

This command starts dispatcherd workers to process background tasks from the database.

Fork model (AAP-79584): dispatcherd creates the worker pool with
``multiprocessing``'s ``fork`` context, so this process must not hold a database
connection *or* a database-touching thread when it calls
``dispatcherd.run_service()``. The runtime log level is therefore applied once,
synchronously, before the fork (and its connection closed), and the periodic
refresh thread is started by each forked worker child through
:class:`apps.tasks.dispatcherd_worker.LogLevelSyncWorker`.
"""

import logging
import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tasks.dispatcherd_config import setup_dispatcherd_config

logger = logging.getLogger(__name__)

# ES-SUP-2: ``--log-level`` may only retune these named loggers. The root logger
# stays at ``settings.LOG_LEVEL`` so a worker can never be quieter than the level
# the operator configured for the deployment.
ES_SUP_2_LOGGER_NAMES = ("apps", "dispatcherd", "awx.main.dispatch")


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
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            default=None,
            help=(
                "Log level for the dispatcherd and apps loggers. Defaults to "
                "settings.LOG_LEVEL (the METRICS_SERVICE_LOG_LEVEL env var); the root "
                "logger is never modified (ES-SUP-2)."
            ),
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        try:
            # Record this process's epoch before workers are forked so they
            # inherit it. A runtime log level override written before this
            # moment is treated as stale and ignored (AAP-79584).
            os.environ["METRICS_SERVICE_PROCESS_STARTED_AT"] = timezone.now().isoformat()

            # ES-SUP-2: the worker process inherits Django's logging
            # configuration, whose root logger is already at LOG_LEVEL. Setting
            # the level on named loggers keeps an explicit --log-level effective
            # without calling logging.basicConfig(level=...), which would rewrite
            # the ROOT logger and could drop the whole process below the level
            # the operator configured (METRICS_SERVICE_LOG_LEVEL).
            log_level = str(options.get("log_level") or getattr(settings, "LOG_LEVEL", "INFO")).upper()
            for logger_name in ES_SUP_2_LOGGER_NAMES:
                logging.getLogger(logger_name).setLevel(log_level)
            # Setup dispatcherd configuration
            setup_dispatcherd_config()

            # Apply any active runtime log level override for this process before
            # it starts accepting work. This is the only database access the
            # parent performs, it is synchronous, and its connection is closed
            # below before dispatcherd forks the worker pool.
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
                # ``close_old_connections()`` would be a no-op when
                # CONN_MAX_AGE > 0, so close every connection unconditionally.
                from django.db import connection, connections

                if not connection.in_atomic_block:
                    connections.close_all()

            # Import dispatcherd after configuration
            import dispatcherd

            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting dispatcherd with {options['workers']} workers (max_tasks: {options['max_tasks']})"
                )
            )

            # NOTE: do not start any thread here. run_service() forks the worker
            # pool, and a thread polling the database pre-fork would hand every
            # child a socket shared with this process. The refresh thread is
            # started per child in LogLevelSyncWorker.on_start() instead
            # (see apps/tasks/dispatcherd_worker.py).

            # Start dispatcherd service
            dispatcherd.run_service()

        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Failed to import dispatcherd: {e}"))
            sys.exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to start dispatcherd: {e}"))
            sys.exit(1)
