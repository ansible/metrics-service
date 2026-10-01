"""Serializers for the analytics API."""

from rest_framework import serializers

from apps.analytics.models import AnalyticsPayload


class CollectionDemandResultSerializer(serializers.Serializer):
    """Serialize the outcome for one analytics collection demand period."""

    action = serializers.ChoiceField(
        choices=["already_collected", "cron_covered", "existing_task", "scheduled", "suppressed", "triggered"]
    )
    task_id = serializers.IntegerField(required=False)
    task_url = serializers.URLField(required=False)
    status = serializers.CharField(required=False)
    scheduled_time = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(required=False)


class CollectionDemandSerializer(serializers.Serializer):
    """Serialize collection demand outcomes for windowed and snapshot collectors."""

    previous = CollectionDemandResultSerializer(required=False)
    current = CollectionDemandResultSerializer(required=False)
    snapshot = CollectionDemandResultSerializer(required=False)


class CollectorDiscoverySerializer(serializers.Serializer):
    """Serialize one enabled collector and its hyperlinked API endpoints."""

    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    mode = serializers.CharField(read_only=True)
    accepts_since_until = serializers.BooleanField(read_only=True)
    rows_url = serializers.HyperlinkedIdentityField(
        view_name="analytics:v1:rows",
        lookup_field="name",
        lookup_url_kwarg="collector",
    )
    collect_url = serializers.HyperlinkedIdentityField(
        view_name="analytics:v1:collect",
        lookup_field="name",
        lookup_url_kwarg="collector",
    )


class AnalyticsPayloadSerializer(serializers.ModelSerializer):
    """Serialise one stored raw collection envelope."""

    class Meta:
        model = AnalyticsPayload
        fields = ["id", "collector", "source", "since", "until", "started_at", "finished_at", "payload"]
        read_only_fields = fields
