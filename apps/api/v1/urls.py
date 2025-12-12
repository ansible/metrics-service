"""
URL configuration for API v1.
"""

from django.urls import include, path

from .router import router

app_name = "v1"

urlpatterns = [
    # Include router URLs for RBAC-managed resources
    path("", include(router.urls)),
    # Dynamic settings API (backwards compatible at /api/v1/settings/)
    path("settings/", include("apps.dynamic_settings.urls")),
    # Nested API endpoints
    path("tasks/", include("apps.api.v1.tasks.urls", namespace="tasks")),
]
