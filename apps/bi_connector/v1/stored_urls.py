"""URL configuration for BI connector stored billing data endpoints.

Mounts at /api/v1/bi/stored/ via apps/urls.py.

Endpoints:
    GET /api/v1/bi/stored/host-metrics/                — list StoredHostMetric
    GET /api/v1/bi/stored/host-metrics/<id>/           — detail
    GET /api/v1/bi/stored/job-host-summaries/          — list StoredJobHostSummary
    GET /api/v1/bi/stored/indirect-audits/             — list StoredIndirectAudit
    GET /api/v1/bi/stored/batches/                     — list CollectionBatch (read-only for BI)
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .stored_views import (
    CollectionBatchViewSet,
    StoredHostMetricViewSet,
    StoredIndirectAuditViewSet,
    StoredJobHostSummaryViewSet,
)

app_name = "stored"

router = DefaultRouter()
router.register(r"host-metrics", StoredHostMetricViewSet, basename="host-metrics")
router.register(r"job-host-summaries", StoredJobHostSummaryViewSet, basename="job-host-summaries")
router.register(r"indirect-audits", StoredIndirectAuditViewSet, basename="indirect-audits")
router.register(r"batches", CollectionBatchViewSet, basename="batches")

urlpatterns = [path("", include(router.urls))]
