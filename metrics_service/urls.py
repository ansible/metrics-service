"""
URL configuration for metrics_service project.
"""

from ansible_base.lib.dynamic_config.dynamic_urls import api_version_urls, root_urls
from ansible_base.resource_registry.urls import urlpatterns as resource_api_urls
from apps.core.views import APIRootView
from django.urls import include, path

urlpatterns = [
    # DRF browsable API authentication
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    # Dashboard interface
    path("dashboard/", include("apps.dashboard.urls")),
    # Core API endpoints (users, orgs, teams, health, ping) - includes api/v1/
    path("", include("apps.core.urls")),
    # Dynamic settings API
    path("api/", include("apps.dynamic_settings.urls")),
    # Tasks API
    path("api/", include("apps.tasks.urls")),
    # Django-Ansible-Base URLs (order matters - most specific first)
    path("api/v1/", include(resource_api_urls)),  # More specific DAB resources
    path("api/v1/", include(api_version_urls)),  # General DAB v1 endpoints
    # Root URLs
    path("", include(root_urls)),
    # Prometheus urls
    path("", include("django_prometheus.urls")),
]

# Override empty router views from DAB with dynamic API root
urlpatterns += [
    path("api/v1/", APIRootView.as_view(view_name="v1"), name="api-v1-index"),
    path("api/", APIRootView.as_view(view_name="api"), name="api-index"),
    path("", APIRootView.as_view(view_name="metrics_service"), name="root-index"),
]
