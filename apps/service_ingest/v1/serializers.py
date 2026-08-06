"""Serializers for the service ingest v1 API."""

import logging

from rest_framework import serializers

from apps.service_ingest.models import ExternalEvent, ServiceDefinition

logger = logging.getLogger(__name__)


class ServiceDefinitionSerializer(serializers.ModelSerializer):
    """
    Serializer for ServiceDefinition registration.

    rollup_config is optional on write — the view will call infer_rollup_config
    and populate it before saving if the caller omits it or sends an empty dict.
    """

    class Meta:
        model = ServiceDefinition
        fields = [
            "service_name",
            "event_name",
            "display_name",
            "version",
            "segment_event_name",
            "payload_schema",
            "rollup_config",
            "active",
            "registered_at",
            "last_seen_at",
        ]
        read_only_fields = ["active", "registered_at", "last_seen_at"]
        extra_kwargs = {
            "rollup_config": {"required": False, "default": dict},
        }
        # Skip DRF's auto-generated UniqueTogetherValidator — the view
        # handles upsert via update_or_create on (service_name, event_name).
        validators = []

    def validate_payload_schema(self, value):
        """payload_schema must be a dict (can be empty for MVP)."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("payload_schema must be a JSON object (dict).")
        return value


class ExternalEventSerializer(serializers.ModelSerializer):
    """
    Serializer for inbound telemetry events.

    service_name, event_name, and schema_version are write-only helper fields
    used to resolve the ServiceDefinition FK; they are not stored on the model.
    received_at is a read-only alias for ExternalEvent.created.
    """

    # Write-only lookup helpers — not model fields
    service_name = serializers.CharField(write_only=True)
    event_name = serializers.CharField(write_only=True)
    schema_version = serializers.CharField(write_only=True, required=False, allow_blank=True, default="")

    # Read-only alias for created
    received_at = serializers.DateTimeField(source="created", read_only=True)

    class Meta:
        model = ExternalEvent
        fields = [
            "id",
            "service_name",
            "event_name",
            "schema_version",
            "payload_type",
            "collection_start",
            "collection_end",
            "event_timestamp",
            "payload",
            "status",
            "received_at",
        ]
        read_only_fields = ["id", "status", "received_at"]

    def validate(self, attrs):
        """
        Cross-field validation:
        - Resolve ServiceDefinition from service_name + event_name.
        - Enforce that batch payloads supply collection_start/end and
          event payloads supply event_timestamp.
        """
        service_name = attrs.pop("service_name")
        event_name = attrs.pop("event_name")
        attrs.pop("schema_version", None)

        try:
            definition = ServiceDefinition.objects.get(
                service_name=service_name,
                event_name=event_name,
                active=True,
            )
        except ServiceDefinition.DoesNotExist:
            raise serializers.ValidationError(
                {
                    "service_name": (
                        f"No active ServiceDefinition found for "
                        f"service_name={service_name!r}, event_name={event_name!r}. "
                        "Call /register/ first."
                    )
                }
            )

        attrs["service"] = definition

        payload_type = attrs.get("payload_type")
        if payload_type == "batch":
            if not attrs.get("collection_start") or not attrs.get("collection_end"):
                raise serializers.ValidationError(
                    "Batch events must provide both collection_start and collection_end."
                )
        elif payload_type == "event":
            if not attrs.get("event_timestamp"):
                raise serializers.ValidationError(
                    "Per-event payloads must provide event_timestamp."
                )

        return attrs
