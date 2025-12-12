"""
URL configuration for API v1.
"""

from django.urls import include, path

from .router import router
from .views import SettingView

app_name = "v1"

# Settings is a singleton resource, so we need custom URL mappings
# to allow PUT/PATCH on the list endpoint
urlpatterns = [
    # Include router URLs for RBAC-managed resources
    path("", include(router.urls)),
    path(
        "settings/",
        SettingView.as_view({"get": "list", "put": "update", "patch": "partial_update"}),
        name="settings-list",
    ),
    path(
        "settings/reload/",
        SettingView.as_view({"post": "reload"}),
        name="settings-reload",
    ),
    path(
        "settings/rollback/<int:change_id>/",
        SettingView.as_view({"post": "rollback"}),
        name="settings-rollback",
    ),
    # Nested API endpoints
    path("tasks/", include("apps.api.v1.tasks.urls", namespace="tasks")),
]
