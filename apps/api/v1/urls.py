"""
URL configuration for API v1.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .viewsets import OrganizationViewSet, SettingView, TeamViewSet, UserViewSet

# Create DRF router for endpoints
router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"organizations", OrganizationViewSet, basename="organization")
router.register(r"teams", TeamViewSet, basename="team")

urlpatterns = [
    # Settings is a singleton resource with GET-only access
    path(
        "settings/",
        SettingView.as_view({"get": "list"}),
        name="settings-list",
    ),
    # Tasks API endpoints
    path("tasks/", include("apps.api.v1.tasks.urls")),
    # Include router URLs for other endpoints
    path("", include(router.urls)),
]
