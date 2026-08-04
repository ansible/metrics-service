"""URL patterns for dynamic_settings v1 API."""
from django.urls import path

from .views import SettingsView

app_name = "dynamic_settings_v1"

urlpatterns = [
    path("", SettingsView.as_view(), name="settings"),
]
