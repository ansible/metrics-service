"""Serializers for the analytics API."""

from rest_framework import serializers

from apps.analytics.models import AnalyticsPayload


class CollectorDiscoverySerializer(serializers.Serializer):
    """Serialize one enabled collector and its hyperlinked API endpoints."""

    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    payload_shape = serializers.ChoiceField(
        choices=("object", "array"),
        read_only=True,
        help_text="Top-level JSON shape of payload: object or array.",
    )
    key_field = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="Field represented by top-level object keys, or null when not applicable.",
    )
    mode = serializers.CharField(read_only=True)
    accepts_since_until = serializers.BooleanField(read_only=True)
    last_collect = serializers.DateTimeField(read_only=True, allow_null=True)
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
