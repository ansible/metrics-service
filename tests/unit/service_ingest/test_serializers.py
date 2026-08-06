"""Tests for service_ingest serializers.

Validates ServiceDefinitionSerializer and ExternalEventSerializer field
validation, required-field enforcement, FK resolution, and cross-field
timestamp checks.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.service_ingest.models import ServiceDefinition
from apps.service_ingest.v1.serializers import (
    ExternalEventSerializer,
    ServiceDefinitionSerializer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registration_data(**overrides):
    """Return minimal valid ServiceDefinition registration data."""
    data = {
        "service_name": "aap-mcp-server",
        "event_name": "mcp_tool_called",
        "display_name": "MCP Tool Called",
        "version": "1.0.0",
        "segment_event_name": "AAP MCP Tool Called",
        "payload_schema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "duration_ms": {"type": "integer"},
            },
        },
    }
    data.update(overrides)
    return data


def _event_data(**overrides):
    """Return minimal valid ExternalEvent payload data."""
    data = {
        "service_name": "aap-mcp-server",
        "event_name": "mcp_tool_called",
        "payload_type": "event",
        "event_timestamp": timezone.now().isoformat(),
        "payload": {"tool_name": "run_playbook", "duration_ms": 1234},
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service_definition(db):
    """Create an active ServiceDefinition for serializer lookup tests."""
    return ServiceDefinition.objects.create(
        service_name="aap-mcp-server",
        event_name="mcp_tool_called",
        display_name="MCP Tool Called",
        version="1.0.0",
        segment_event_name="AAP MCP Tool Called",
        payload_schema={
            "type": "object",
            "properties": {"tool_name": {"type": "string"}},
        },
        rollup_config={
            "strategy": "count_by_field",
            "group_by": ["tool_name"],
            "inferred": True,
        },
        active=True,
    )


# ---------------------------------------------------------------------------
# ServiceDefinitionSerializer
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestServiceDefinitionSerializer:
    """Tests for ServiceDefinitionSerializer validation."""

    def test_valid_data(self):
        """All required fields provided — serializer is valid."""
        serializer = ServiceDefinitionSerializer(data=_registration_data())
        assert serializer.is_valid(), serializer.errors

    def test_missing_required_field(self):
        """Omitting segment_event_name makes the serializer invalid."""
        data = _registration_data()
        del data["segment_event_name"]
        serializer = ServiceDefinitionSerializer(data=data)
        assert not serializer.is_valid()
        assert "segment_event_name" in serializer.errors

    def test_non_dict_payload_schema(self):
        """payload_schema must be a dict — a string value is rejected."""
        data = _registration_data(payload_schema="not a dict")
        serializer = ServiceDefinitionSerializer(data=data)
        assert not serializer.is_valid()
        assert "payload_schema" in serializer.errors

    def test_rollup_config_optional(self):
        """rollup_config can be omitted — defaults to empty dict."""
        data = _registration_data()
        data.pop("rollup_config", None)
        serializer = ServiceDefinitionSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        # Default callable produces {}
        assert serializer.validated_data.get("rollup_config", {}) == {}


# ---------------------------------------------------------------------------
# ExternalEventSerializer
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestExternalEventSerializer:
    """Tests for ExternalEventSerializer validation and service lookup."""

    def test_valid_event(self, service_definition):
        """Valid event payload resolves the matching ServiceDefinition."""
        serializer = ExternalEventSerializer(data=_event_data())
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["service"] == service_definition

    def test_valid_batch(self, service_definition):
        """Valid batch payload with collection timestamps is accepted."""
        now = timezone.now()
        data = _event_data(
            payload_type="batch",
            collection_start=(now - timedelta(hours=1)).isoformat(),
            collection_end=now.isoformat(),
        )
        data.pop("event_timestamp", None)
        serializer = ExternalEventSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["service"] == service_definition

    def test_missing_event_name_error(self, service_definition):
        """Omitting event_name produces a validation error."""
        data = _event_data()
        del data["event_name"]
        serializer = ExternalEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "event_name" in serializer.errors

    def test_unregistered_service_error(self):
        """Unknown service_name + event_name combination is rejected."""
        data = _event_data(
            service_name="unknown-svc",
            event_name="unknown_event",
        )
        serializer = ExternalEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "service_name" in serializer.errors
        error_msg = str(serializer.errors["service_name"])
        assert "No active ServiceDefinition" in error_msg

    def test_inactive_service_error(self):
        """ServiceDefinition with active=False is not matched."""
        ServiceDefinition.objects.create(
            service_name="inactive-svc",
            event_name="some_event",
            display_name="Inactive Service",
            version="1.0.0",
            segment_event_name="Inactive Event",
            active=False,
        )
        data = _event_data(
            service_name="inactive-svc",
            event_name="some_event",
        )
        serializer = ExternalEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "service_name" in serializer.errors

    def test_batch_without_timestamps_error(self, service_definition):
        """Batch payload without collection_start/end is rejected."""
        data = _event_data(payload_type="batch")
        data.pop("collection_start", None)
        data.pop("collection_end", None)
        serializer = ExternalEventSerializer(data=data)
        assert not serializer.is_valid()
        error_str = str(serializer.errors)
        assert "collection_start" in error_str or "Batch events" in error_str

    def test_event_without_timestamp_error(self, service_definition):
        """Per-event payload without event_timestamp is rejected."""
        data = _event_data(payload_type="event")
        data.pop("event_timestamp", None)
        serializer = ExternalEventSerializer(data=data)
        assert not serializer.is_valid()
        error_str = str(serializer.errors)
        assert "event_timestamp" in error_str or "Per-event" in error_str



@pytest.mark.django_db
class TestPayloadValidation:
    """Tests for payload validation against schema."""

    def test_payload_validation_enabled_valid_payload(self):
        defn = ServiceDefinition.objects.create(
            service_name="test-svc", event_name="test-event",
            display_name="Test", version="1.0",
            segment_event_name="Test Event",
            payload_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            validate_payload=True,
        )
        data = {"service_name": "test-svc", "event_name": "test-event", "payload_type": "event",
                "event_timestamp": "2026-08-06T10:00:00Z", "payload": {"name": "hello"}}
        serializer = ExternalEventSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_payload_validation_enabled_invalid_payload_rejected(self):
        defn = ServiceDefinition.objects.create(
            service_name="test-svc", event_name="test-event",
            display_name="Test", version="1.0",
            segment_event_name="Test Event",
            payload_schema={"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]},
            validate_payload=True,
        )
        data = {"service_name": "test-svc", "event_name": "test-event", "payload_type": "event",
                "event_timestamp": "2026-08-06T10:00:00Z", "payload": {"count": "not-an-integer"}}
        serializer = ExternalEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "payload" in serializer.errors

    def test_payload_validation_disabled_invalid_payload_accepted(self):
        defn = ServiceDefinition.objects.create(
            service_name="test-svc", event_name="test-event",
            display_name="Test", version="1.0",
            segment_event_name="Test Event",
            payload_schema={"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]},
            validate_payload=False,
        )
        data = {"service_name": "test-svc", "event_name": "test-event", "payload_type": "event",
                "event_timestamp": "2026-08-06T10:00:00Z", "payload": {"count": "not-an-integer"}}
        serializer = ExternalEventSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_invalid_json_schema_rejected_at_registration(self):
        data = {"service_name": "s", "event_name": "e", "display_name": "D", "version": "1",
                "segment_event_name": "E",
                "payload_schema": {"type": "object", "properties": {"x": {"type": "not_a_type"}}}}
        serializer = ServiceDefinitionSerializer(data=data)
        assert not serializer.is_valid()
        assert "payload_schema" in serializer.errors

    def test_invalid_rollup_config_strategy_rejected(self):
        data = {"service_name": "s", "event_name": "e", "display_name": "D", "version": "1",
                "segment_event_name": "E", "payload_schema": {},
                "rollup_config": {"strategy": "invalid_strategy"}}
        serializer = ServiceDefinitionSerializer(data=data)
        assert not serializer.is_valid()
        assert "rollup_config" in serializer.errors

    def test_rollup_config_non_list_group_by_rejected(self):
        data = {"service_name": "s", "event_name": "e", "display_name": "D", "version": "1",
                "segment_event_name": "E", "payload_schema": {},
                "rollup_config": {"strategy": "count_by_field", "group_by": "not_a_list"}}
        serializer = ServiceDefinitionSerializer(data=data)
        assert not serializer.is_valid()
        assert "rollup_config" in serializer.errors
