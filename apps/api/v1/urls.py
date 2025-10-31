"""
URL configuration for API v1.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrganizationViewSet, SettingView, UserViewSet

app_name = "v1"

# Create DRF router for non-nested endpoints
router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"organizations", OrganizationViewSet, basename="organization")

# Settings is a singleton resource, so we need custom URL mappings
# to allow PUT/PATCH on the list endpoint
urlpatterns = [
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
    # Include router URLs for other endpoints
    path("", include(router.urls)),
]
