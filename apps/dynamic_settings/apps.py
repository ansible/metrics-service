"""
Dynamic Settings app configuration.
"""

from django.apps import AppConfig


class DynamicSettingsConfig(AppConfig):
    """Configuration for the dynamic_settings app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dynamic_settings"
    verbose_name = "Dynamic Settings"

    def ready(self):
        """
        Perform initialization when the app is ready.

        This method is called when Django starts up and the app is fully loaded.
        It initializes default feature flag settings in the database.
        """
        self._initialize_default_settings()

    def _initialize_default_settings(self):
        """Initialize default settings in the database."""
        import logging

        from django.db import connection
        from django.db.utils import OperationalError, ProgrammingError

        logger = logging.getLogger(__name__)

        try:
            # Check if database is ready and settings table exists
            with connection.cursor() as cursor:
                query = "SELECT tablename FROM pg_tables WHERE tablename='dynamic_settings_setting';"
                cursor.execute(query)
                if not cursor.fetchone():
                    logger.debug("Settings table not found - skipping initialization")
                    return

            # Initialize default settings
            from .utils import initialize_default_settings

            initialize_default_settings()

        except (OperationalError, ProgrammingError) as e:
            # Database not ready yet (migrations not run)
            logger.debug(f"Database not ready for settings initialization: {e}")
        except Exception as e:
            # Don't crash the app if initialization fails
            logger.error(f"Error initializing default settings: {e}")
