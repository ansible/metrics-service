"""
Dynamic Settings app configuration.
"""

from django.apps import AppConfig


class DynamicSettingsConfig(AppConfig):
    """Configuration for the dynamic_settings app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dynamic_settings"
    verbose_name = "Dynamic Settings"
