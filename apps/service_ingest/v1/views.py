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
from apps.service_ingest.rollup import infer_rollup_config
from apps.service_ingest.v1.serializers import ExternalEventSerializer, ServiceDefinitionSerializer

logger = logging.getLogger(__name__)


class RegisterView(APIView):
    """
    POST /api/v1/ingest/register/

    AAP services call this at startup to declare their identity and payload
    schema. Idempotent — repeated calls update the record and return 200;
    a first registration returns 201.
    """

    authentication_classes = [IngestAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ServiceDefinitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        payload_schema = validated.get("payload_schema", {})
        rollup_config = validated.get("rollup_config") or {}

        # Auto-infer rollup_config when the caller omits it or sends an empty dict
        if not rollup_config:
            rollup_config = infer_rollup_config(payload_schema)
            logger.debug(
                "Auto-inferred rollup_config for %s/%s",
                validated["service_name"],
                validated["event_name"],
            )

        definition, created = ServiceDefinition.objects.update_or_create(
            service_name=validated["service_name"],
            event_name=validated["event_name"],
            defaults={
                "display_name": validated["display_name"],
                "version": validated["version"],
                "segment_event_name": validated["segment_event_name"],
                "payload_schema": payload_schema,
                "rollup_config": rollup_config,
                "active": True,
                "last_seen_at": now(),
            },
        )

        logger.info(
            "Registered service %s/%s (version=%s)",
            definition.service_name,
            definition.event_name,
            definition.version,
        )

        response_serializer = ServiceDefinitionSerializer(definition)
        status_code = 201 if created else 200
        return Response(response_serializer.data, status=status_code)


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
