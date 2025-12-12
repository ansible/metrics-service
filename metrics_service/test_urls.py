"""
Simplified URL configuration for testing that avoids oauth2 provider conflicts.
"""

from django.urls import include, path

urlpatterns = [
    # Core app (authentication, etc.)
    path("", include("apps.core.urls")),
    # Health and system endpoints
    path("", include("apps.health.urls")),
    # Dashboard interface
    path("dashboard/", include("apps.dashboard.urls")),
    # Dynamic settings API
    path("api/", include("apps.dynamic_settings.urls")),
    # Tasks API
    path("api/", include("apps.tasks.urls")),
    # Prometheus metrics
    path("", include("django_prometheus.urls")),
]
