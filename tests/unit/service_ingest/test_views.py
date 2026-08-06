"""Tests for service_ingest views.

Covers RegisterView, IngestView, and StatusView including auth, feature
flag gating, upsert behaviour, batch task dispatch, and status aggregation.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIClient

from apps.service_ingest.models import ExternalEvent, ServiceDefinition
from apps.service_ingest.permissions import IsServiceIngestEnabled
from apps.service_ingest.v1.views import IngestView, RegisterView

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGISTER_URL = "/api/v1/ingest/register/"
EVENTS_URL = "/api/v1/ingest/events/"
STATUS_URL = "/api/v1/ingest/status/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registration_payload(**overrides):
    """Return minimal valid registration POST data."""
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


def _event_payload(**overrides):
    """Return minimal valid event POST data."""
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
    """Create an active ServiceDefinition."""
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
# RegisterView
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestRegisterView:
    """Tests for POST /api/v1/ingest/register/."""

    def test_post_creates_definition_201(self, authenticated_client):
        """First registration creates a ServiceDefinition and returns 201."""
        response = authenticated_client.post(REGISTER_URL, data=_registration_payload(), format="json")
        assert response.status_code == 201

        defn = ServiceDefinition.objects.get(
            service_name="aap-mcp-server",
            event_name="mcp_tool_called",
        )
        # rollup_config should be auto-inferred from payload_schema
        assert defn.rollup_config.get("inferred") is True
        assert "strategy" in defn.rollup_config
        assert "group_by" in defn.rollup_config

    def test_post_upserts_200(self, authenticated_client):
        """Registering same (service_name, event_name) twice upserts and returns 200."""
        resp1 = authenticated_client.post(REGISTER_URL, data=_registration_payload(version="1.0.0"), format="json")
        assert resp1.status_code == 201

        resp2 = authenticated_client.post(REGISTER_URL, data=_registration_payload(version="2.0.0"), format="json")
        assert resp2.status_code == 200

        defn = ServiceDefinition.objects.get(
            service_name="aap-mcp-server",
            event_name="mcp_tool_called",
        )
        assert defn.version == "2.0.0"

    def test_feature_flag_disabled_403(self, authenticated_client):
        """Returns 403 when SERVICE_INGEST feature flag is disabled."""
        with (
            mock.patch.object(
                RegisterView,
                "permission_classes",
                [IsAuthenticated, IsServiceIngestEnabled],
            ),
            mock.patch(
                "apps.tasks.task_groups.get_feature_enabled_from_db",
                return_value=False,
            ),
        ):
            response = authenticated_client.post(REGISTER_URL, data=_registration_payload(), format="json")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# IngestView
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestIngestView:
    """Tests for POST /api/v1/ingest/events/."""

    def test_post_creates_event_202(self, authenticated_client, service_definition):
        """Posting a valid event creates an ExternalEvent with status=pending."""
        response = authenticated_client.post(EVENTS_URL, data=_event_payload(), format="json")
        assert response.status_code == 202
        assert ExternalEvent.objects.filter(service=service_definition, status="pending").exists()

    def test_post_batch_dispatches_task_202(self, authenticated_client, service_definition):
        """Batch payload creates event and dispatches a background task."""
        now = timezone.now()
        data = _event_payload(
            payload_type="batch",
            collection_start=(now - timedelta(hours=1)).isoformat(),
            collection_end=now.isoformat(),
        )
        with mock.patch("apps.tasks.tasks.submit_task_to_dispatcher") as mock_submit:
            response = authenticated_client.post(EVENTS_URL, data=data, format="json")

        assert response.status_code == 202

        from apps.tasks.models import Task

        task = Task.objects.filter(function_name="send_external_batch_to_segment").first()
        assert task is not None
        mock_submit.assert_called_once()

    def test_feature_flag_disabled_403(self, authenticated_client, service_definition):
        """Returns 403 when SERVICE_INGEST feature flag is disabled."""
        with (
            mock.patch.object(
                IngestView,
                "permission_classes",
                [IsAuthenticated, IsServiceIngestEnabled],
            ),
            mock.patch(
                "apps.tasks.task_groups.get_feature_enabled_from_db",
                return_value=False,
            ),
        ):
            response = authenticated_client.post(EVENTS_URL, data=_event_payload(), format="json")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# StatusView
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestStatusView:
    """Tests for GET /api/v1/ingest/status/."""

    def test_get_returns_counts(self, authenticated_client, service_definition):
        """Returns counts of events grouped by status."""
        ExternalEvent.objects.create(
            service=service_definition,
            payload_type="event",
            payload={"x": 1},
            status="pending",
        )
        ExternalEvent.objects.create(
            service=service_definition,
            payload_type="event",
            payload={"x": 2},
            status="pending",
        )
        ExternalEvent.objects.create(
            service=service_definition,
            payload_type="event",
            payload={"x": 3},
            status="sent",
        )

        response = authenticated_client.get(STATUS_URL)
        assert response.status_code == 200
        assert response.data["events_pending"] == 2
        assert response.data["events_sent"] == 1
        assert response.data["events_processing"] == 0
        assert response.data["events_failed"] == 0

    def test_get_with_service_name_filter(self, authenticated_client):
        """service_name query param scopes the result to one service."""
        defn_mcp = ServiceDefinition.objects.create(
            service_name="aap-mcp-server",
            event_name="mcp_tool_called",
            display_name="MCP",
            version="1.0.0",
            segment_event_name="MCP Tool Called",
            active=True,
        )
        defn_eda = ServiceDefinition.objects.create(
            service_name="aap-eda-server",
            event_name="eda_activation_daily_summary",
            display_name="EDA",
            version="1.0.0",
            segment_event_name="EDA Activation",
            active=True,
        )
        ExternalEvent.objects.create(
            service=defn_mcp,
            payload_type="event",
            payload={"x": 1},
            status="pending",
        )
        ExternalEvent.objects.create(
            service=defn_eda,
            payload_type="event",
            payload={"x": 2},
            status="pending",
        )
        ExternalEvent.objects.create(
            service=defn_eda,
            payload_type="event",
            payload={"x": 3},
            status="sent",
        )

        response = authenticated_client.get(f"{STATUS_URL}?service_name=aap-mcp-server")
        assert response.status_code == 200
        assert response.data["events_pending"] == 1
        assert response.data["events_sent"] == 0


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestUnauthenticated:
    """Verify unauthenticated requests are rejected."""

    def test_unauthenticated_request_denied(self):
        """Request without credentials returns 401 or 403."""
        client = APIClient()
        for url in (REGISTER_URL, EVENTS_URL, STATUS_URL):
            response = client.get(url) if url == STATUS_URL else client.post(url, data={}, format="json")
            assert response.status_code in (401, 403), f"{url} returned {response.status_code}, expected 401 or 403"



@pytest.mark.django_db
@pytest.mark.unit
class TestSchemaValidationViews:
    """Tests for payload schema validation through the view layer."""

    def test_register_with_validate_payload_stores_flag(self, authenticated_client):
        data = _registration_payload()
        data["validate_payload"] = True
        response = authenticated_client.post(REGISTER_URL, data=data, format="json")
        assert response.status_code == 201
        defn = ServiceDefinition.objects.get(service_name="aap-mcp-server", event_name="mcp_tool_called")
        assert defn.validate_payload is True

    def test_ingest_with_validation_enabled_valid_payload_202(self, authenticated_client):
        ServiceDefinition.objects.create(
            service_name="aap-mcp-server", event_name="mcp_tool_called",
            display_name="Test", version="1.0", segment_event_name="Test",
            payload_schema={"type": "object", "properties": {"tool_name": {"type": "string"}}},
            validate_payload=True,
        )
        data = {"service_name": "aap-mcp-server", "event_name": "mcp_tool_called",
                "payload_type": "event", "event_timestamp": "2026-08-06T10:00:00Z",
                "payload": {"tool_name": "test"}}
        response = authenticated_client.post(EVENTS_URL, data=data, format="json")
        assert response.status_code == 202

    def test_ingest_with_validation_enabled_invalid_payload_400(self, authenticated_client):
        ServiceDefinition.objects.create(
            service_name="aap-mcp-server", event_name="mcp_tool_called",
            display_name="Test", version="1.0", segment_event_name="Test",
            payload_schema={"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]},
            validate_payload=True,
        )
        data = {"service_name": "aap-mcp-server", "event_name": "mcp_tool_called",
                "payload_type": "event", "event_timestamp": "2026-08-06T10:00:00Z",
                "payload": {"count": "not-an-integer"}}
        response = authenticated_client.post(EVENTS_URL, data=data, format="json")
        assert response.status_code == 400
