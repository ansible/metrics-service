"""
URL configuration for dynamic settings API v1.
"""

from django.urls import path

from .viewsets import SettingViewSet

app_name = "dynamic_settings_v1"

# Note: These URLs are mounted at /api/v1/settings/
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
