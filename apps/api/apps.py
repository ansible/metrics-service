"""
API app configuration for metrics_service.
"""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Configuration for the API app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"
    verbose_name = "API"
