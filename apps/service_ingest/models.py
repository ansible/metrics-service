"""Models for external service telemetry ingest."""

import uuid

from django.db import models

from apps.service_ingest.enums import KnownEvent, KnownService


def _uuid4_str() -> str:
    return str(uuid.uuid4())


class ServiceDefinition(models.Model):
    """
    Service self-registration record.

    Each AAP service that sends telemetry registers here at startup,
    declaring its identity, the schema of its payloads, and the rollup
    strategy metrics-service should apply before sending to Segment.
    """

    # service_name and event_name use choices for known services, but the
    # field is not restricted to those values — new services can register freely.
    service_name = models.CharField(
        max_length=128,
        choices=KnownService.choices,
        help_text="Machine identifier matching the service's gateway identity.",
    )
    event_name = models.CharField(
        max_length=128,
        choices=KnownEvent.choices,
        help_text="Logical event type within the service (one service may have several).",
    )
    display_name = models.CharField(max_length=256)
    version = models.CharField(max_length=64, help_text="Schema version declared by the service.")
    segment_event_name = models.CharField(
        max_length=256,
        help_text="Event name emitted to Segment/Amplitude (human-readable, stable).",
    )
    payload_schema = models.JSONField(
        default=dict,
        help_text="JSON Schema describing the payload object. Stored for documentation; auto-generates rollup_config.",
    )
    rollup_config = models.JSONField(
        default=dict,
        help_text="Auto-inferred aggregation strategy (infer_rollup_config). Can be overridden in the registration payload.",
    )
    active = models.BooleanField(default=True)
    validate_payload = models.BooleanField(
        default=False,
        help_text="When True, inbound payloads are validated against payload_schema. "
                  "When False, schema is stored for documentation only.",
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "service_ingest_definition"
        unique_together = [("service_name", "event_name")]
        ordering = ["service_name", "event_name"]

    def __str__(self) -> str:
        return f"{self.service_name}/{self.event_name}"


class ExternalEvent(models.Model):
    """Telemetry payload received from an external AAP service."""

    PAYLOAD_TYPE_CHOICES = [
        ("batch", "Batch"),
        ("event", "Event"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    service = models.ForeignKey(
        ServiceDefinition,
        on_delete=models.PROTECT,
        related_name="events",
        help_text="The registered service that sent this payload.",
    )
    payload_type = models.CharField(max_length=10, choices=PAYLOAD_TYPE_CHOICES)

    # Batch: time window covered by this payload
    collection_start = models.DateTimeField(null=True, blank=True)
    collection_end = models.DateTimeField(null=True, blank=True)

    # Per-event: when the event occurred on the sender
    event_timestamp = models.DateTimeField(null=True, blank=True)

    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    segment_anonymous_id = models.CharField(max_length=64, default=_uuid4_str)
    retry_count = models.IntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["service", "status"], name="si_event_svc_status_idx"),
            models.Index(fields=["payload_type", "status", "created"], name="si_event_type_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.service} {self.payload_type} [{self.status}] @ {self.created}"
