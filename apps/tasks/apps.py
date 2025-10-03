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
        # Import signal handlers to register them
        from . import signals  # noqa
