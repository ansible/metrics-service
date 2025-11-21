"""
Health and system URLs.
"""

from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    # Admin interface
    path("admin/", admin.site.urls),
    path("health", views.health_check, name="health_check"),
]
