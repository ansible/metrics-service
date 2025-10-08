"""
Django app configuration for tasks app.
"""

from django.apps import AppConfig


class TasksConfig(AppConfig):
    """Configuration for the tasks app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tasks"
    label = "tasks"
    verbose_name = "Task Management"

    def ready(self):
        """
        Perform initialization when the app is ready.

        This method is called when Django starts up and the app is fully loaded.
        It's the right place to perform any app initialization.
        """
        # Import signal handlers if any
        from . import signals  # noqa

        # Initialize system tasks on startup
        self._initialize_system_tasks()

    def _initialize_system_tasks(self):
        """
        Initialize system-defined tasks if the database is ready.

        This method is called during app startup to ensure system tasks
        like cleanup and metrics collection are always present.
        """
        import logging

        from django.db import connection
        from django.db.utils import OperationalError, ProgrammingError

        logger = logging.getLogger(__name__)

        try:
            # Check if database is ready and tasks table exists
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks_task';"
                    if connection.vendor == "sqlite"
                    else "SELECT tablename FROM pg_tables WHERE tablename='tasks_task';"
                    if connection.vendor == "postgresql"
                    else "SHOW TABLES LIKE 'tasks_task';"
                )
                if not cursor.fetchone():
                    logger.info("Tasks table not found - skipping system task initialization")
                    return

            # Import and run system task creation
            from .tasks import create_system_tasks

            results = create_system_tasks()

            if "error" not in results:
                total_processed = results.get("created", 0) + results.get("updated", 0)
                if total_processed > 0:
                    logger.info(
                        f"System tasks initialized: {results.get('created', 0)} created, "
                        f"{results.get('updated', 0)} updated, {results.get('skipped', 0)} skipped"
                    )
            else:
                logger.warning(f"System task initialization failed: {results.get('error')}")

        except (OperationalError, ProgrammingError) as e:
            # Database not ready yet (migrations not run)
            logger.debug(f"Database not ready for system task initialization: {e}")
        except Exception as e:
            # Don't crash the app if system task initialization fails
            logger.error(f"Error initializing system tasks: {e}")
            pass
