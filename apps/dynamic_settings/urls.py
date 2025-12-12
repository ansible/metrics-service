"""
URL configuration for dynamic_settings app.
"""

from django.urls import include, path

urlpatterns = [
    path("", include("apps.dynamic_settings.v1.urls")),
]
