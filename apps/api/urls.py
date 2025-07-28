"""
Main API URL configuration for my_service.
"""

from django.urls import path, include

app_name = "api"

urlpatterns = [
    # API version 1 (default)
    path("v1/", include("apps.api.v1.urls", namespace="v1")),
]
