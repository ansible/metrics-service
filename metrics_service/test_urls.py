"""
Simplified URL configuration for testing that avoids oauth2 provider conflicts.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    # Core app (authentication, etc.)
    path("", include("apps.core.urls")),
    # Health and system endpoints
    path("", include("apps.health.urls")),
    # API schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Admin interface
    path("admin/", admin.site.urls),
    # API endpoints
    path("api/", include("apps.api.urls")),
]
