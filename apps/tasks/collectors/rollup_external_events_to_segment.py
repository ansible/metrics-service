"""
Aggregate and send per-event ExternalEvents to Segment.

This task processes yesterday's pending per-event ExternalEvents, applies the
RollupEngine strategy declared on each ServiceDefinition, then sends each
aggregated row to Segment as a single analytics.track() call.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from django.utils import timezone

from ..utils import create_task_result, log_task_execution

logger = logging.getLogger(__name__)


def rollup_external_events_to_segment(execution_id=None, **kwargs) -> dict:
    """
    Aggregate and send yesterday's pending per-event ExternalEvents to Segment.

    For each ServiceDefinition with pending events:
    - Apply definition.rollup_config via RollupEngine
    - Send each aggregated row to Segment as one analytics.track() call
    - Mark processed events as sent/failed

    Args:
        execution_id: Task execution ID (passed by task runner)
        **kwargs: Additional task data (unused)

    Returns:
        dict: Task result with date, groups_sent, and events_processed
    """
    from apps.service_ingest.models import ExternalEvent, ServiceDefinition  # noqa: F401
    from apps.service_ingest.rollup import RollupEngine
    from apps.tasks.collectors.send_anonymized_to_segment import send_to_segment

    yesterday = date.today() - timedelta(days=1)

    log_task_execution(
        "rollup_external_events_to_segment",
        "processing",
        f"Rolling up per-event ExternalEvents for {yesterday}",
    )

    # Fetch all pending per-event records for yesterday
    pending_qs = (
        ExternalEvent.objects.filter(
            payload_type="event",
            status="pending",
            created__date=yesterday,
        )
        .select_related("service")
        .order_by("service_id", "created")
    )

    if not pending_qs.exists():
        log_task_execution(
            "rollup_external_events_to_segment",
            "skipped",
            f"No pending per-event ExternalEvents for {yesterday}",
        )
        return create_task_result(
            "success",
            {
                "date": str(yesterday),
                "groups_sent": 0,
                "events_processed": 0,
            },
        )

    # Group events by ServiceDefinition
    groups: dict[int, list] = defaultdict(list)
    service_map: dict[int, Any] = {}
    for event in pending_qs:
        groups[event.service_id].append(event)
        service_map[event.service_id] = event.service

    groups_sent = 0
    total_processed = 0
    engine = RollupEngine()
    now = timezone.now()

    for service_id, events in groups.items():
        definition = service_map[service_id]
        event_ids = [e.id for e in events]

        try:
            # Re-query as a QS so RollupEngine can annotate/aggregate as needed
            events_qs = ExternalEvent.objects.filter(id__in=event_ids)
            rollup_rows = engine.rollup(events_qs, definition)

            for rollup_dict in rollup_rows:
                anonymous_id = events[0].segment_anonymous_id
                segment_result = send_to_segment(
                    user_id=anonymous_id,
                    event_name=definition.segment_event_name,
                    segment_data=rollup_dict,
                )
                if segment_result.get("status") != "success":
                    raise RuntimeError(segment_result.get("error", "send_to_segment returned non-success"))

            # Mark all events in this group as sent
            ExternalEvent.objects.filter(id__in=event_ids).update(
                status="sent",
                sent_at=now,
                error_message="",
            )
            groups_sent += 1
            total_processed += len(event_ids)

            logger.info(
                "Rolled up %d events for service %s → Segment event '%s'",
                len(event_ids),
                definition,
                definition.segment_event_name,
            )

        except Exception as exc:
            error_msg = str(exc)
            logger.exception(
                "Failed to roll up events for service %s (IDs %s): %s",
                definition,
                event_ids,
                error_msg,
            )
            ExternalEvent.objects.filter(id__in=event_ids).update(
                status="failed",
                error_message=error_msg[:500],
            )

    log_task_execution(
        "rollup_external_events_to_segment",
        "completed",
        f"Groups sent: {groups_sent}, Events processed: {total_processed}",
    )

    return create_task_result(
        "success",
        {
            "date": str(yesterday),
            "groups_sent": groups_sent,
            "events_processed": total_processed,
        },
    )
