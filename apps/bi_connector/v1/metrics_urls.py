"""
URL configuration for BI connector Layer 1 (metrics-service DB) endpoints.

Mounts at /api/v1/bi/metrics/ via apps/urls.py.

Endpoints:
    GET /api/v1/bi/metrics/daily/                    - list DailyMetricsSummary (filterable by date)
    GET /api/v1/bi/metrics/daily/<summary_date>/     - single day detail with raw collector blobs
    GET /api/v1/bi/metrics/hourly/                   - list HourlyMetricsCollection (filterable)
    GET /api/v1/bi/metrics/hourly/<id>/              - single hourly record with raw_data

Analytics aggregate endpoints (sourced from HourlyMetricsCollection.raw_data):
    GET /api/v1/bi/metrics/modules/                  - per-module compute hours and task runs
    GET /api/v1/bi/metrics/organizations/            - per-org job and task totals
    GET /api/v1/bi/metrics/compute-hours/            - aggregate automation compute hours summary
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .analytics_urls import urlpatterns as analytics_urlpatterns
from .metrics_views import DailyMetricsSummaryViewSet, HourlyMetricsCollectionViewSet

app_name = "metrics"

router = DefaultRouter()
router.register(r"daily", DailyMetricsSummaryViewSet, basename="daily-metrics")
router.register(r"hourly", HourlyMetricsCollectionViewSet, basename="hourly-metrics")

urlpatterns = [
    path("", include(router.urls)),
    *analytics_urlpatterns,
]
