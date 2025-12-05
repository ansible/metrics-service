"""
Automation Reports Django App Configuration
"""

from django.apps import AppConfig


class AutomationReportsConfig(AppConfig):
    """
    Configuration for Automation Reports app.

    Stores AWX/Controller job data collected directly from source database.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.automation_reports"
    label = "automation_reports"
    verbose_name = "Automation Reports"
