"""
Django app configuration for events app.
"""

from django.apps import AppConfig


class EventsConfig(AppConfig):
    """Configuration for the events app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.events"
    label = "events"
    verbose_name = "Events"
