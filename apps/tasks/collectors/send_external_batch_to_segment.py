"""
Send a single ExternalEvent batch payload to Segment immediately.

Dispatched by IngestView as soon as a batch payload is received.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def send_external_batch_to_segment(execution_id: int | None = None, event_id: int | None = None, **kwargs) -> dict:
    """
    Send a batch ExternalEvent payload to Segment.

    Args:
        execution_id: TaskExecution ID (provided by execute_db_task, passed through)
        event_id: Primary key of the ExternalEvent to send
    """
    from apps.service_ingest.models import ExternalEvent
    from apps.tasks.collectors.send_anonymized_to_segment import send_to_segment
    from apps.tasks.utils import create_task_result

    if not event_id:
        logger.error("send_external_batch_to_segment called without event_id")
        return create_task_result("error", error="event_id is required")

    try:
        event = ExternalEvent.objects.select_related("service").get(pk=event_id)
    except ExternalEvent.DoesNotExist:
        logger.error("ExternalEvent %s not found", event_id)
        return create_task_result("error", error=f"ExternalEvent {event_id} not found")

    if event.status not in ("pending", "failed"):
        logger.info("ExternalEvent %s already in status=%s, skipping", event_id, event.status)
        return create_task_result("success", {"skipped": True, "status": event.status})

    event.status = "processing"
    event.save(update_fields=["status", "modified"])

    result = send_to_segment(
        user_id=event.segment_anonymous_id,
        event_name=event.service.segment_event_name,
        segment_data=event.payload,
    )

    if result.get("status") == "success":
        event.status = "sent"
        event.sent_at = timezone.now()
        event.error_message = ""
        event.save(update_fields=["status", "sent_at", "error_message", "modified"])
        logger.info("Sent ExternalEvent %s (%s) to Segment", event_id, event.service.segment_event_name)
    else:
        event.retry_count += 1
        event.status = "failed"
        event.error_message = result.get("error", "Unknown error")
        event.save(update_fields=["status", "retry_count", "error_message", "modified"])
        logger.warning("Failed to send ExternalEvent %s: %s", event_id, event.error_message)

    return result
