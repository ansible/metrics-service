"""URL configuration for BI connector admin/settings endpoints."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .collector_settings_views import AdminCollectionBatchViewSet, CollectorSettingsView

app_name = "collector-settings"

router = DefaultRouter()
router.register(r"batches", AdminCollectionBatchViewSet, basename="admin-batches")

urlpatterns = [
    path("", CollectorSettingsView.as_view(), name="collector-settings"),
    path("", include(router.urls)),
]
