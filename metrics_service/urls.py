"""
URL configuration for metrics_service project.
"""

from ansible_base.lib.dynamic_config.dynamic_urls import (
    api_version_urls,
    root_urls,
)
from ansible_base.resource_registry.urls import (
    urlpatterns as resource_api_urls,
)
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    # Core app (authentication, etc.)
    path("", include("apps.core.urls")),
    # Health and system endpoints
    path("", include("apps.health.urls")),
    # Dashboard interface
    path("dashboard/", include("apps.dashboard.urls")),
    # API schema (needs to be at root level for DRF Spectacular)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # API endpoints (includes documentation)
    path("api/", include("apps.api.urls")),
    # Django-Ansible-Base URLs (order matters - most specific first)
    path("api/v1/", include(resource_api_urls)),  # More specific DAB resources
    path("api/v1/", include(api_version_urls)),  # General DAB v1 endpoints
    # Root URLs
    path("", include(root_urls)),
]
