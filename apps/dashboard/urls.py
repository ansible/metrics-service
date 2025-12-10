"""
URL configuration for dashboard app.
"""

from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
]
