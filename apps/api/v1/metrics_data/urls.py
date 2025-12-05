"""
URL routing for metrics_data API endpoints.

Registers BI and UI endpoints for metrics data access.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BIMetricDataViewSet, UIMetricDataViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r"bi", BIMetricDataViewSet, basename="metrics-bi")
router.register(r"ui", UIMetricDataViewSet, basename="metrics-ui")

urlpatterns = [
    path("", include(router.urls)),
]
