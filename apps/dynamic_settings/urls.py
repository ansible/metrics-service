"""
URL configuration for dynamic_settings app.
"""

from django.urls import include, path

app_name = "dynamic_settings"

urlpatterns = [
    path("v1/settings/", include("apps.dynamic_settings.v1.urls", namespace="v1")),
]
