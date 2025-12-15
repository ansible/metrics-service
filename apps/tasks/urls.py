"""
URL configuration for tasks app.
"""

from django.urls import include, path

app_name = "tasks"

urlpatterns = [
    path("v1/tasks/", include("apps.tasks.v1.urls", namespace="v1")),
]
