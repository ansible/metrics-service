"""Serializers for BI connector stored billing data (Layer 1)."""

from rest_framework import serializers

from apps.bi_connector.models import (
    CollectionBatch,
    StoredHostMetric,
    StoredIndirectAudit,
    StoredJobHostSummary,
)


class CollectionBatchSerializer(serializers.ModelSerializer):
    """Read-only serializer for CollectionBatch — exposes all fields to BI consumers."""

    class Meta:
        model = CollectionBatch
        fields = [
            "id",
            "collector_type",
            "batch_type",
            "status",
            "since",
            "until",
            "records_imported",
            "cursor",
            "task_id",
            "started_at",
            "completed_at",
            "error_message",
            "created",
            "modified",
        ]
        read_only_fields = fields


class StoredHostMetricSerializer(serializers.ModelSerializer):
    """Read-only serializer for StoredHostMetric billing data."""

    class Meta:
        model = StoredHostMetric
        fields = [
            "id",
            "hostname",
            "host_id",
            "first_automation",
            "last_automation",
            "automated_counter",
            "deleted_counter",
            "last_deleted",
            "deleted",
            "ansible_product_serial",
            "ansible_machine_id",
            "ansible_host_variable",
            "ansible_connection_variable",
            "collection_batch_id",
            "created",
            "modified",
        ]
        read_only_fields = fields


class StoredJobHostSummarySerializer(serializers.ModelSerializer):
    """Read-only serializer for StoredJobHostSummary billing data."""

    class Meta:
        model = StoredJobHostSummary
        fields = [
            "id",
            "summary_id",
            "host_id",
            "job_id",
            "host_name",
            "organization_id",
            "inventory_id",
            "modified",
            "collection_batch_id",
            "created",
        ]
        read_only_fields = fields


class StoredIndirectAuditSerializer(serializers.ModelSerializer):
    """Read-only serializer for StoredIndirectAudit billing data."""

    class Meta:
        model = StoredIndirectAudit
        fields = [
            "id",
            "audit_id",
            "host_id",
            "job_id",
            "organization_id",
            "created",
            "collection_batch_id",
        ]
        read_only_fields = fields
