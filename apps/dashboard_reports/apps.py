"""
Dashboard reports app configuration.
"""

from django.apps import AppConfig


class DashboardReportsConfig(AppConfig):
    """Django app configuration for the dashboard_reports app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard_reports"
    verbose_name = "Dashboard Reports"
