"""
Simplified URL configuration for testing that avoids oauth2 provider conflicts.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Admin interface
    path("admin/", admin.site.urls),
    # API endpoints
    path("api/", include("apps.api.urls")),
]
