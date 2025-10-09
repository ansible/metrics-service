"""
Main API URL configuration for metrics_service.
"""

from django.urls import include, path
from drf_spectacular.views import (
    SpectacularRedocView,
    SpectacularSwaggerView,
)

app_name = "api"

urlpatterns = [
    # API documentation (schema is handled in main urls.py)
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # API version 1 (default)
    path("v1/", include("apps.api.v1.urls", namespace="v1")),
]
