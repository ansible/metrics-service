"""
URL configuration for metrics_service project.
"""

from ansible_base.lib.dynamic_config.dynamic_urls import api_version_urls, root_urls
from ansible_base.resource_registry.urls import urlpatterns as resource_api_urls
from django.urls import include, path

urlpatterns = [
    # DRF browsable API authentication
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    # Health and system endpoints
    path("", include("apps.health.urls")),
    # Dashboard interface
    path("dashboard/", include("apps.dashboard.urls")),
    # Core API endpoints (users, orgs, teams) - includes v1/
    path("api/", include("apps.core.urls")),
    # Dynamic settings API
    path("api/", include("apps.dynamic_settings.urls")),
    # API-specific endpoints (tasks)
    path("api/", include("apps.api.urls")),
    # Django-Ansible-Base URLs (order matters - most specific first)
    path("api/v1/", include(resource_api_urls)),  # More specific DAB resources
    path("api/v1/", include(api_version_urls)),  # General DAB v1 endpoints
    # Root URLs
    path("", include(root_urls)),
    # Prometheus urls
    path("", include("django_prometheus.urls")),
]
