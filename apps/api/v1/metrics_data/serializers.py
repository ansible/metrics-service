"""
Serializers for metrics_storage models.

Provides serialization for metrics data API endpoints.
"""

from rest_framework import serializers

from apps.metrics_storage.models import CollectionRun, MetricData, MetricSource, MetricType


class MetricTypeSerializer(serializers.ModelSerializer):
    """Serializer for MetricType model."""

    class Meta:
        model = MetricType
        fields = ["id", "name", "description", "category", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class MetricSourceSerializer(serializers.ModelSerializer):
    """Serializer for MetricSource model."""

    class Meta:
        model = MetricSource
        fields = [
            "id",
            "source_type",
            "source_id",
            "source_name",
            "metadata",
            "first_seen",
            "last_seen",
            "is_active",
        ]
        read_only_fields = fields


class CollectionRunSerializer(serializers.ModelSerializer):
    """Serializer for CollectionRun model."""

    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = CollectionRun
        fields = [
            "id",
            "started_at",
            "completed_at",
            "status",
            "metrics_collected",
            "collectors_run",
            "parameters_used",
            "error_message",
            "duration_seconds",
        ]
        read_only_fields = fields

    def get_duration_seconds(self, obj):
        """Calculate duration in seconds if completed."""
        if obj.completed_at and obj.started_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None


class MetricDataSerializer(serializers.ModelSerializer):
    """Serializer for MetricData model."""

    metric_type_name = serializers.CharField(source="metric_type.name", read_only=True)
    metric_category = serializers.CharField(source="metric_type.category", read_only=True)
    collection_run_id = serializers.IntegerField(source="collection_run.id", read_only=True)
    collection_started_at = serializers.DateTimeField(source="collection_run.started_at", read_only=True)

    class Meta:
        model = MetricData
        fields = [
            "id",
            "collected_at",
            "metric_type_name",
            "metric_category",
            "collection_run_id",
            "collection_started_at",
            "data",
            "data_size_bytes",
            "collection_duration_ms",
            "was_successful",
            "error_message",
        ]
        read_only_fields = fields


class MetricDataDetailSerializer(MetricDataSerializer):
    """Detailed serializer for MetricData with full relationships."""

    metric_type = MetricTypeSerializer(read_only=True)
    collection_run = CollectionRunSerializer(read_only=True)

    class Meta(MetricDataSerializer.Meta):
        fields = MetricDataSerializer.Meta.fields + ["metric_type", "collection_run"]
