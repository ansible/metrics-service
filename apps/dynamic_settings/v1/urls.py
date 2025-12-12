"""
URL configuration for dynamic settings API v1.
"""

from django.urls import path

from .viewsets import SettingViewSet

# Note: These URLs are mounted at /api/v1/settings/ for backwards compatibility
urlpatterns = [
    path(
        "",
        SettingViewSet.as_view({"get": "list", "put": "update", "patch": "partial_update"}),
        name="settings-list",
    ),
    path(
        "reload/",
        SettingViewSet.as_view({"post": "reload"}),
        name="settings-reload",
    ),
    path(
        "rollback/<int:change_id>/",
        SettingViewSet.as_view({"post": "rollback"}),
        name="settings-rollback",
    ),
]
