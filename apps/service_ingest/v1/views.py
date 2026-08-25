"""Views for the service ingest v1 API."""

import logging

import crum
from django.db.models import Count, Max
from django.utils.timezone import now
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.service_ingest.authentication import IngestAuthentication
from apps.service_ingest.permissions import IsServiceIngestEnabled
from apps.service_ingest.models import ExternalEvent, ServiceDefinition
from apps.service_ingest.v1.serializers import ExternalEventSerializer

logger = logging.getLogger(__name__)


class RegisterView(APIView):
    """
    POST /api/v1/ingest/register/

    Lightweight heartbeat endpoint for AAP services. Services call this at
    startup to declare which events they will send. Validates that all declared
    events exist in the schema registry (loaded from YAML files at container startup).

    Request body:
    {
        "service_name": "aap-mcp-server",
        "events": ["mcp_tool_called", "mcp_server_status"]
    }

    Returns 200 if all events are registered, 400 if any are unknown.
    Updates last_seen_at timestamp for all declared ServiceDefinitions.
    """

    authentication_classes = [IngestAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Validate request structure
        service_name = request.data.get("service_name")
        events = request.data.get("events", [])

        if not service_name:
            return Response(
                {"error": "service_name is required"},
                status=400,
            )

        if not isinstance(events, list) or not events:
            return Response(
                {"error": "events must be a non-empty list of event names"},
                status=400,
            )

        # Validate that all declared events exist in schema registry
        missing_events = []
        registered_definitions = []

        for event_name in events:
            try:
                definition = ServiceDefinition.objects.get(
                    service_name=service_name,
                    event_name=event_name,
                    active=True,
                )
                registered_definitions.append(definition)
            except ServiceDefinition.DoesNotExist:
                missing_events.append(event_name)

        if missing_events:
            return Response(
                {
                    "error": (
                        f"Service '{service_name}' declared unknown events: {missing_events}. "
                        "Events must be defined in the schema registry (schemas/service_ingest/)."
                    ),
                    "missing_events": missing_events,
                },
                status=400,
            )

        # Update last_seen_at for all registered events
        now_timestamp = now()
        for definition in registered_definitions:
            definition.last_seen_at = now_timestamp
            definition.save(update_fields=["last_seen_at"])

        logger.info(
            "Service %s registered with %d events: %s",
            service_name,
            len(events),
            ", ".join(events),
        )

        return Response(
            {
                "status": "registered",
                "service_name": service_name,
                "events": events,
                "timestamp": now_timestamp.isoformat(),
            },
            status=200,
        )


class IngestView(APIView):
    """
    POST /api/v1/ingest/events/

    Accepts a telemetry payload from a registered AAP service. Stores it as
    a pending ExternalEvent. Batch payloads are dispatched immediately to the
    background task queue for rollup + Segment forwarding.
    """

    authentication_classes = [IngestAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ExternalEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event = serializer.save()

        # Update last_seen_at on the parent ServiceDefinition
        event.service.last_seen_at = now()
        event.service.save(update_fields=["last_seen_at"])

        if event.payload_type == "batch":
            self._dispatch_batch_task(event)

        logger.info(
            "Accepted %s event id=%s for service %s",
            event.payload_type,
            event.pk,
            event.service,
        )

        return Response(
            {
                "id": event.pk,
                "status": "accepted",
                "payload_type": event.payload_type,
            },
            status=202,
        )

    def _dispatch_batch_task(self, event: ExternalEvent) -> None:
        """Create and submit a background Task to process the batch event."""
        try:
            from apps.tasks.models import Task
            from apps.tasks.tasks import submit_task_to_dispatcher

            with crum.impersonate(None):
                task = Task.objects.create(
                    name=f"process_batch_event_{event.pk}",
                    function_name="send_external_batch_to_segment",
                    task_data={"event_id": event.pk},
                    is_system_task=True,
                )

            submit_task_to_dispatcher(task)
            logger.debug("Dispatched batch task id=%s for event id=%s", task.pk, event.pk)
        except Exception:
            # Log but don't fail the HTTP response — event is safely stored as pending
            logger.exception("Failed to dispatch batch task for event id=%s; will retry later", event.pk)


class StatusView(APIView):
    """
    GET /api/v1/ingest/status/

    Returns counts of ExternalEvents grouped by status. Accepts an optional
    ``?service_name=`` query param to scope the result to a specific service;
    without it, aggregates across all services.
    """

    authentication_classes = [IngestAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service_name = request.query_params.get("service_name")

        qs = ExternalEvent.objects.all()
        if service_name:
            qs = qs.filter(service__service_name=service_name)

        # Status counts
        counts_qs = qs.values("status").annotate(count=Count("id"))
        counts = {row["status"]: row["count"] for row in counts_qs}

        # Most recent sent_at across the filtered events
        last_sent = qs.filter(status="sent").aggregate(last=Max("sent_at"))["last"]

        return Response(
            {
                "events_pending": counts.get("pending", 0),
                "events_processing": counts.get("processing", 0),
                "events_sent": counts.get("sent", 0),
                "events_failed": counts.get("failed", 0),
                "last_sent_at": last_sent,
            }
        )
