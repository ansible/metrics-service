"""
URL configuration for API v1.
"""

from django.urls import include, path

app_name = "v1"

urlpatterns = [
    # Dynamic settings API
    path("settings/", include("apps.dynamic_settings.urls")),
    # Task management API
    path("tasks/", include("apps.api.v1.tasks.urls", namespace="tasks")),
]
