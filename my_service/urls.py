"""
URL configuration for my_service project.
"""

from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from ansible_base.lib.dynamic_config.dynamic_urls import (
    api_urls,
    api_version_urls,
    root_urls,
)
from ansible_base.resource_registry.urls import (
    urlpatterns as resource_api_urls,
)

urlpatterns = [
    # Admin interface
    path("admin/", admin.site.urls),
    # API endpoints
    path("api/", include("apps.api.urls")),
    # Health checks
    path("health/", include("apps.health.urls")),
    # OpenAPI schema and documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Django-Ansible-Base URLs
    path("api/v1/", include(api_version_urls)),
    path("api/v1/", include(resource_api_urls)),
    path("api/", include(api_urls)),
    path("", include(root_urls)),
]
