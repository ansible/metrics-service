"""URL patterns for dynamic_settings v1 API."""
from django.urls import path

from .views import SettingsCategoryView, SettingsView

app_name = "dynamic_settings_v1"

urlpatterns = [
    path("", SettingsView.as_view(), name="settings"),
    path("<str:category>/", SettingsCategoryView.as_view(), name="settings-category"),
]
