"""
Main API URL configuration for metrics_service.
"""

from django.urls import include, path

app_name = "api"

urlpatterns = [
    # API version 1 (default)
    path("v1/", include("apps.api.v1.urls", namespace="v1")),
]
