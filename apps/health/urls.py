"""
Health and system URLs.
"""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    # Admin interface
    path("admin/", admin.site.urls),
]



