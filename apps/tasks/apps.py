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

        # Initialize system tasks and start scheduler
        self._initialize_system_and_scheduler()

    def _initialize_system_and_scheduler(self):
        """
        Initialize system tasks and start the simple scheduler.
        """
        from django.db import connection
        from django.db.utils import OperationalError, ProgrammingError

        from metrics_service.logger import get_logger

        logger = get_logger(__name__)

        try:
            # Check if database is ready and tasks table exists
            with connection.cursor() as cursor:
                if connection.vendor == "sqlite":
                    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks_task';"
                elif connection.vendor == "postgresql":
                    query = "SELECT tablename FROM pg_tables WHERE tablename='tasks_task';"
                else:
                    query = "SHOW TABLES LIKE 'tasks_task';"

                cursor.execute(query)
                if not cursor.fetchone():
                    logger.debug("Tasks table not found - skipping initialization")
                    return

            # Initialize system tasks using the new simple approach
            from .simple_scheduler import initialize_system_tasks, start_scheduler

            initialize_system_tasks()

            # Start the simple scheduler
            start_scheduler()
            logger.info("Task system initialized with simple scheduler")

        except (OperationalError, ProgrammingError) as e:
            # Database not ready yet (migrations not run)
            logger.debug(f"Database not ready for task system initialization: {e}")
        except Exception as e:
            # Don't crash the app if initialization fails
            logger.error(f"Error initializing task system: {e}")
