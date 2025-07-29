"""
Health app configuration for metrics_service.
"""

from django.apps import AppConfig


class HealthConfig(AppConfig):
    """Configuration for the health app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.health"
    verbose_name = "Health"
