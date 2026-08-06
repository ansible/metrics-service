"""
Retry sweep for failed ExternalEvent payloads.

Runs daily (4 AM) after the rollup task. Re-queues failed batch events
for immediate dispatch and resets failed per-event records to pending
so the next rollup picks them up.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def retry_failed_ingest_events(execution_id: int | None = None, max_retries: int = MAX_RETRIES, **kwargs) -> dict:
    from apps.service_ingest.models import ExternalEvent
    from apps.tasks.utils import create_task_result

    failed = ExternalEvent.objects.filter(
        status="failed",
        retry_count__lt=max_retries,
    ).select_related("service")

    total = failed.count()
    if total == 0:
        logger.info("No failed ingest events eligible for retry")
        return create_task_result("success", {"retried_batch": 0, "retried_event": 0})

    retried_batch = 0
    retried_event = 0

    batch_events = failed.filter(payload_type="batch")
    for event in batch_events:
        try:
            import crum
            from apps.tasks.models import Task
            from apps.tasks.tasks import submit_task_to_dispatcher

            with crum.impersonate(None):
                task = Task.objects.create(
                    name=f"Retry batch from {event.service.service_name} (event {event.pk}, attempt {event.retry_count + 1})",
                    function_name="send_external_batch_to_segment",
                    task_data={"event_id": event.pk},
                    is_system_task=True,
                )
            submit_task_to_dispatcher(task)
            retried_batch += 1
            logger.debug("Re-dispatched batch event %s (attempt %s)", event.pk, event.retry_count + 1)
        except Exception:
            logger.exception("Failed to re-dispatch batch event %s", event.pk)

    per_event_pks = list(failed.filter(payload_type="event").values_list("pk", flat=True))
    if per_event_pks:
        retried_event = ExternalEvent.objects.filter(pk__in=per_event_pks).update(
            status="pending",
            error_message="",
            modified=timezone.now(),
        )
        logger.info("Reset %d failed per-event records to pending for next rollup", retried_event)

    logger.info("Retry sweep: %d batch re-dispatched, %d per-event reset to pending", retried_batch, retried_event)
    return create_task_result("success", {
        "retried_batch": retried_batch,
        "retried_event": retried_event,
    })
