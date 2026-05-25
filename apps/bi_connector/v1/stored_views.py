"""
BI connector Layer 1 viewsets for stored billing data.

Read-only endpoints serving data collected by the billing collector pipeline.
All viewsets require token authentication and the BI_CONNECTOR feature flag.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.bi_connector.models import (
    CollectionBatch,
    StoredHostMetric,
    StoredIndirectAudit,
    StoredJobHostSummary,
)
from apps.bi_connector.v1.mixins import BiConnectorEnabledMixin
from apps.bi_connector.v1.stored_serializers import (
    CollectionBatchSerializer,
    StoredHostMetricSerializer,
    StoredIndirectAuditSerializer,
    StoredJobHostSummarySerializer,
)


class StoredHostMetricViewSet(BiConnectorEnabledMixin, ReadOnlyModelViewSet):
    """
    Read-only ViewSet for StoredHostMetric billing data.

    Exposes per-host automation metrics collected by the billing pipeline.
    Filterable by hostname, deleted status, and automation date ranges.

    Filters: hostname, deleted, last_automation, first_automation
    """

    queryset = StoredHostMetric.objects.all()
    serializer_class = StoredHostMetricSerializer
    permission_classes = [IsAuthenticated]
    versioning_class = None
    filterset_fields = {
        "hostname": ["exact", "icontains"],
        "deleted": ["exact"],
        "last_automation": ["gte", "lte"],
        "first_automation": ["gte", "lte"],
    }
    ordering_fields = ["hostname", "last_automation", "first_automation", "automated_counter"]
    ordering = ["-last_automation"]


class StoredJobHostSummaryViewSet(BiConnectorEnabledMixin, ReadOnlyModelViewSet):
    """
    Read-only ViewSet for StoredJobHostSummary billing data.

    Exposes per-job host summary records collected by the billing pipeline.
    Filterable by job, organization, and modification date range.

    Filters: job_id, organization_id, modified, host_name
    """

    queryset = StoredJobHostSummary.objects.all()
    serializer_class = StoredJobHostSummarySerializer
    permission_classes = [IsAuthenticated]
    versioning_class = None
    filterset_fields = {
        "job_id": ["exact"],
        "organization_id": ["exact"],
        "modified": ["gte", "lte"],
        "host_name": ["icontains"],
    }
    ordering_fields = ["modified", "job_id", "organization_id", "summary_id"]
    ordering = ["-modified"]


class StoredIndirectAuditViewSet(BiConnectorEnabledMixin, ReadOnlyModelViewSet):
    """
    Read-only ViewSet for StoredIndirectAudit billing data.

    Exposes indirect managed node audit records collected by the billing pipeline.
    Filterable by job, organization, and creation timestamp.

    Filters: job_id, organization_id, created
    """

    queryset = StoredIndirectAudit.objects.all()
    serializer_class = StoredIndirectAuditSerializer
    permission_classes = [IsAuthenticated]
    versioning_class = None
    filterset_fields = {
        "job_id": ["exact"],
        "organization_id": ["exact"],
        "created": ["gte", "lte"],
    }
    ordering = ["-created"]


class CollectionBatchViewSet(BiConnectorEnabledMixin, ReadOnlyModelViewSet):
    """
    Read-only ViewSet for CollectionBatch.

    Exposes batch history so BI consumers can inspect collection runs,
    their status, and import counts. Filterable by collector type, status,
    and batch type.

    Filters: collector_type, status, batch_type
    """

    queryset = CollectionBatch.objects.all()
    serializer_class = CollectionBatchSerializer
    permission_classes = [IsAuthenticated]
    versioning_class = None
    filterset_fields = {
        "collector_type": ["exact"],
        "status": ["exact"],
        "batch_type": ["exact"],
    }
    ordering = ["-created"]
