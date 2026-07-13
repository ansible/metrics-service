"""
Send anonymized payload to Segment.

Two execution paths exist:

1. APScheduler-native (preferred): ``apscheduler_poll_and_send()`` is called
   directly by UnifiedTaskScheduler on a 5-minute interval.  It holds a
   module-level ``analytics.Client`` (``sync_mode=False``, ``gzip=True``) so the
   SDK's background thread can batch multiple chunks from the same payload into a
   single compressed ``/v1/batch`` POST.  No dispatcherd involvement.

2. Dispatcherd fallback: ``send_anonymized_to_segment()`` remains in
   ``TASK_FUNCTIONS`` so operators can trigger a one-off send via the task API.
   It uses the same persistent client when available.
"""

import hashlib
import logging
import threading
import uuid as uuid_module
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from ..utils import (
    create_task_result,
    log_task_execution,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent Segment client — owned by the web/APScheduler process.
# sync_mode=False lets the SDK batch chunks across track() calls into a single
# gzip-compressed /v1/batch POST.  Each payload's chunks are flushed together
# so they land as one batch request, giving much better compression than
# sync_mode=True (which sends each chunk as its own individual POST).
# ---------------------------------------------------------------------------

_segment_client: "Any | None" = None
_segment_client_lock = threading.Lock()


def _get_segment_client():
    """Return the process-level analytics.Client, creating it on first call."""
    global _segment_client
    if _segment_client is not None:
        return _segment_client
    with _segment_client_lock:
        if _segment_client is not None:
            return _segment_client
        try:
            import segment.analytics as analytics
        except ImportError:
            logger.warning("segment-analytics-python not installed; Segment sending disabled")
            return None
        write_key = getattr(settings, "SEGMENT_WRITE_KEY", None)
        if not write_key:
            logger.warning("SEGMENT_WRITE_KEY not configured; Segment sending disabled")
            return None
        _segment_client = analytics.Client(
            write_key=write_key,
            gzip=True,
            debug=getattr(settings, "DEBUG", False),
            on_error=lambda err, batch: logger.error("Segment client error: %s", err),
        )
        logger.info("Persistent Segment client initialised (gzip=True, sync_mode=False)")
        return _segment_client


def _retry_backoff_minutes(retry_count: int, base_minutes: int = 8, cap_minutes: int = 480) -> int:
    """Exponential backoff for retries: 8, 16, 32, 64, 128, 256, 480 minutes.

    Mirrors the old dispatcherd backoff schedule so Segment outages are handled
    gracefully without hammering the endpoint every 5 minutes.
    """
    return min(base_minutes * (2 ** (retry_count - 1)), cap_minutes)


def _jitter_minutes(segment_user_id: str, max_minutes: int = 1440) -> int:
    """Return a stable per-installation offset in [1, max_minutes].

    Derived from the installation's segment_user_id so every payload from the
    same installation uses the same offset. Default 1440 minutes (24 hours)
    spreads 4000+ customers to ~2-3 sends/minute — well within Segment's
    limits and avoids thundering-herd spikes after the nightly 3 AM cron.
    Daily metrics have no urgency so a same-day send is acceptable.
    """
    digest = hashlib.sha256(segment_user_id.encode("utf-8")).digest()
    return 1 + (int.from_bytes(digest[:4], "big") % max_minutes)


def _chunk_and_track(payload, client) -> int:
    """Chunk a payload and queue track() calls on *client*.

    Uses StorageSegment's chunking algorithm but drives the provided client
    directly, bypassing StorageSegment's own client management so the
    persistent process-level client is used instead.

    Returns the number of chunks queued.
    """
    from metrics_utility.library.storage.segment import StorageSegment

    chunks = StorageSegment()._split_into_chunks(payload.anonymized_data, StorageSegment.REGULAR_MESSAGE_LIMIT)

    anonymous_id = str(uuid_module.uuid4())
    base_message_id = str(payload.created)
    total_chunks = len(chunks)

    event_name = payload.segment_event_name
    if getattr(settings, "SEGMENT_TEST_MODE", False):
        event_name = f"{event_name}_Test"

    for i, chunk in enumerate(chunks, 1):
        chunk_message_id = hashlib.sha256(
            f"{base_message_id}_{i}".encode("utf-8", errors="replace")
        ).hexdigest()
        client.track(
            anonymous_id=anonymous_id,
            event=event_name,
            properties={
                "artifact_name": f"metrics_collection_{payload.segment_user_id}",
                "data": chunk,
                "upload_timestamp": datetime.now(tz=dt_timezone.utc).isoformat(),
                "chunk_info": {"chunk_number": i, "total_chunks": total_chunks},
            },
            message_id=chunk_message_id,
            timestamp=payload.created,
        )

    return total_chunks


def apscheduler_poll_and_send(max_payloads: int = 5, stale_minutes: int = 10) -> None:
    """Poll for pending payloads and send to Segment — called directly by APScheduler.

    Runs in the web container's APScheduler thread pool.  Uses the persistent
    module-level client so chunks for each payload are batched together in a
    single gzip-compressed /v1/batch POST.

    The ANONYMIZED_DATA_COLLECTION feature flag is re-checked on every poll so
    disabling it takes effect within one interval without a restart.
    """
    from django.db import close_old_connections

    close_old_connections()

    from apps.tasks.task_groups import get_feature_enabled_from_db

    if not get_feature_enabled_from_db("ANONYMIZED_DATA_COLLECTION"):
        return

    client = _get_segment_client()
    if client is None:
        return

    from apps.tasks.models import AnonymizedMetricsPayload

    now = timezone.now()
    stale_threshold = now - timedelta(minutes=stale_minutes)
    payloads = AnonymizedMetricsPayload.objects.filter(
        Q(status__in=["pending", "retry"]) | Q(status="sending", modified__lt=stale_threshold)
    ).order_by("created")[:max_payloads]

    for payload in payloads:
        if payload.status in ("pending",):
            # Respect the per-installation jitter so all customers don't hit
            # Segment simultaneously after the nightly 3 AM cron.
            due_at = payload.created + timedelta(minutes=_jitter_minutes(payload.segment_user_id))
            if due_at > now:
                logger.debug("Payload %d not yet due (due at %s)", payload.id, due_at.isoformat())
                continue

        elif payload.status == "retry":
            # Exponential backoff: 8, 16, 32 ... 480 minutes from last failure.
            # payload.modified is auto-updated when status is set to "retry", so
            # it captures the most recent failure time without a separate DB field.
            backoff = timedelta(minutes=_retry_backoff_minutes(payload.retry_count))
            retry_due_at = payload.modified + backoff
            if retry_due_at > now:
                logger.debug(
                    "Payload %d in backoff until %s (retry %d, backoff %s)",
                    payload.id,
                    retry_due_at.isoformat(),
                    payload.retry_count,
                    backoff,
                )
                continue

        if payload.status == "retry" and not payload.can_retry():
            payload.status = "failed"
            payload.error_message = "Max retries exceeded"
            payload.save()
            continue

        payload.status = "sending"
        payload.save()

        try:
            n_chunks = _chunk_and_track(payload, client)
            # flush() blocks until all queued chunks for this payload are delivered,
            # so status is only set to "sent" after confirmed receipt.
            client.flush()

            payload.status = "sent"
            payload.sent_at = timezone.now()
            payload.error_message = ""
            payload.save()

            try:
                if payload.daily_summary:
                    payload.daily_summary.status = "sent"
                    payload.daily_summary.save()
            except Exception as summary_err:
                logger.warning("Failed to update daily_summary for payload %d: %s", payload.id, summary_err)

            logger.info("Sent payload %d to Segment via APScheduler (%d chunks)", payload.id, n_chunks)

        except Exception:
            logger.exception("Error sending payload %d to Segment", payload.id)
            payload.retry_count += 1
            payload.status = "retry" if payload.retry_count < payload.max_retries else "failed"
            payload.error_message = "APScheduler send failed — see logs"
            payload.save()


def _get_payloads_to_send(payload_id: int | None, max_payloads: int, stale_threshold) -> list:
    """
    Get anonymized payloads ready to send.

    Args:
        payload_id: Specific payload ID to send (optional)
        max_payloads: Maximum number of payloads to retrieve
        stale_threshold: Datetime threshold for stale "sending" status

    Returns:
        QuerySet of AnonymizedMetricsPayload objects
    """
    from apps.tasks.models import AnonymizedMetricsPayload

    if payload_id:
        return AnonymizedMetricsPayload.objects.filter(
            Q(id=payload_id) & (Q(status__in=["pending", "retry"]) | Q(status="sending", modified__lt=stale_threshold))
        )
    return AnonymizedMetricsPayload.objects.filter(
        Q(status__in=["pending", "retry", "unavailable"]) | Q(status="sending", modified__lt=stale_threshold)
    ).order_by("created")[:max_payloads]


def _handle_successful_send(payload, results: dict) -> None:
    """
    Handle successful payload send to Segment.

    Args:
        payload: AnonymizedMetricsPayload object
        results: Results dictionary to update
    """
    payload.status = "sent"
    payload.sent_at = timezone.now()
    payload.error_message = ""
    payload.save()
    results["sent"] += 1

    # Update daily summary status separately (don't let this failure affect payload)
    try:
        if payload.daily_summary:
            payload.daily_summary.status = "sent"
            payload.daily_summary.save()
    except Exception as summary_error:
        logger.warning(f"Failed to update daily_summary for payload {payload.id}: {summary_error}")


def _handle_failed_send(payload, segment_result: dict, results: dict) -> None:
    """
    Handle failed payload send to Segment.

    Args:
        payload: AnonymizedMetricsPayload object
        segment_result: Result dict from send_to_segment
        results: Results dictionary to update
    """
    error_message = segment_result.get("error", "Unknown error")

    payload.retry_count += 1
    payload.error_message = f"Send failed: {error_message}"

    details = {
        "payload_id": payload.id,
        "summary_date": payload.summary_date,
        "retry_count": payload.retry_count,
        "error": error_message,
    }

    if payload.retry_count >= payload.max_retries:
        # Log an error if we are past the maximum retry limit, else, log a warning about the retry
        payload.status = "failed"
        logger.error("Segment send failed, not retrying", extra=details)
    else:
        payload.status = "retry"
        logger.warning("Segment send failed, retrying", extra=details)

    payload.save()
    results["failed"] += 1


def _handle_unavailable_send(payload, segment_result: dict, results: dict) -> None:
    """
    Handle unavailable Segment service (do not retry).

    Args:
        payload: AnonymizedMetricsPayload object
        segment_result: Result dict from send_to_segment
        results: Results dictionary to update
    """
    error_message = segment_result.get("error", "Service unavailable")

    payload.status = "unavailable"
    payload.error_message = f"Service unavailable: {error_message}"
    payload.save()
    results["skipped"] += 1

    logger.info(f"Segment unavailable for payload {payload.id}, skipping: {error_message}")


def _process_single_payload(payload, results: dict) -> None:
    """
    Process a single payload for sending to Segment.

    Args:
        payload: AnonymizedMetricsPayload object
        results: Results dictionary to update
    """
    # Track if this was a recovered stale payload
    was_stale = payload.status == "sending"
    if was_stale:
        results["recovered"] += 1
        logger.info(f"Recovering stale payload {payload.id} (stuck in 'sending' status)")

    # Check retry limit (for retry status or recovered stale payloads)
    if payload.status == "retry" and not payload.can_retry():
        payload.status = "failed"
        payload.error_message = "Max retries exceeded"
        payload.save()
        results["skipped"] += 1
        return

    # Update status to sending
    payload.status = "sending"
    payload.save()

    try:
        event_name = payload.segment_event_name
        if getattr(settings, "SEGMENT_TEST_MODE", False):
            event_name = f"{event_name}_Test"
            logger.debug(f"SEGMENT_TEST_MODE enabled — using test event name: {event_name}")

        # hashed on the other side, with chunk index
        message_id = str(payload.created)

        segment_result = send_to_segment(
            user_id=payload.segment_user_id,
            event_name=event_name,
            segment_data=payload.anonymized_data,
            segment_meta={
                "timestamp": payload.created,
                "message_id": message_id,
            },
        )

        if segment_result["status"] == "success":
            _handle_successful_send(payload, results)
        elif segment_result["status"] == "unavailable":
            _handle_unavailable_send(payload, segment_result, results)
        else:
            _handle_failed_send(payload, segment_result, results)

    except Exception as e:
        logger.exception(f"Error sending payload {payload.id}")
        error_result = create_task_result("error", error=str(e))
        _handle_failed_send(payload, error_result, results)


def send_to_segment(user_id: str, event_name: str, segment_data: dict, segment_meta: dict = None) -> dict:
    """
    Send data to Segment.com using metrics-utility StorageSegment.

    Args:
        user_id: User ID for Segment tracking
        event_name: Event name for tracking
        segment_data: Dictionary of data to send

    Returns:
        dict: Task result with status, error_category, and error_detail
    """
    try:
        from metrics_utility.library.storage.segment import SEGMENT_AVAILABLE, StorageSegment
    except ImportError:
        logger.warning("metrics-utility segment integration not available")
        return create_task_result("unavailable", error="segment_not_available")

    if not SEGMENT_AVAILABLE or StorageSegment is None:
        return create_task_result("unavailable", error="segment_not_available")

    try:
        import json

        from django.conf import settings

        # Get Segment write key from settings
        write_key = getattr(settings, "SEGMENT_WRITE_KEY", None)
        if not write_key:
            logger.warning("SEGMENT_WRITE_KEY not configured in settings")
            return create_task_result("unavailable", error="SEGMENT_WRITE_KEY not configured in settings")

        # Calculate data size for logging
        data_size = len(json.dumps(segment_data).encode("utf-8"))

        log_task_execution(
            "segment_send",
            "processing",
            f"Sending data to Segment.com using StorageSegment (Size: {data_size} bytes)",
        )

        # Initialize StorageSegment with configuration
        storage = StorageSegment(
            write_key=write_key,
            user_id=user_id,
            debug=getattr(settings, "DEBUG", False),
        )

        # Send data using StorageSegment.put()
        artifact_name = f"metrics_collection_{user_id}"
        chunks = storage.put(
            artifact_name=artifact_name, dict=segment_data, event_name=event_name, segment_meta=segment_meta
        )

        # Log success with chunk information
        chunk_count = len(chunks) if chunks else 1
        logger.info(f"Successfully sent metrics to Segment.com (Size: {data_size} bytes, Chunks: {chunk_count})")
        return create_task_result("success", {"chunks_sent": chunk_count, "data_size_bytes": data_size})

    except Exception as e:
        logger.exception("Error sending data to Segment.com")
        return create_task_result("error", error=str(e))


def send_anonymized_to_segment(**kwargs) -> dict[str, Any]:
    """
    Send anonymized payload to Segment.

    Acquires an advisory lock to prevent concurrent execution, then:
    1. Fetches AnonymizedMetricsPayload records with status=pending/retry
    2. Recovers stale "sending" payloads (stuck for > 10 minutes)
    3. Sends to Segment using send_to_segment helper
    4. Updates payload status based on result

    If no payloads are pending, this is a no-op (returns success with 0 sent).
    If the lock cannot be acquired, the task fails and will be retried.

    Args:
        **kwargs: Task data containing:
            - payload_id (int): Specific payload ID to send (optional)
            - max_payloads (int): Maximum number of payloads to send (default: 5)
            - stale_minutes (int): Minutes before "sending" status is considered stale (default: 10)

    Returns:
        dict: Task result with send statistics
    """
    max_payloads = kwargs.get("max_payloads", 5)
    payload_id = kwargs.get("payload_id")
    stale_minutes = kwargs.get("stale_minutes", 10)

    try:
        stale_threshold = timezone.now() - timedelta(minutes=stale_minutes)

        # Check for pending payloads early to avoid unnecessary work
        payloads = _get_payloads_to_send(payload_id, max_payloads, stale_threshold)
        if not payloads:
            log_task_execution("send_anonymized_to_segment", "skipped", "No pending payloads to send")
            return create_task_result(
                "success",
                {
                    "task_type": "send_anonymized_to_segment",
                    "results": {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0},
                    "total_processed": 0,
                },
            )

        log_task_execution("send_anonymized_to_segment", "processing", "Sending anonymized payloads to Segment")

        # Initialize results
        results = {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}

        # Process each payload
        for payload in payloads:
            _process_single_payload(payload, results)

        log_task_execution(
            "send_anonymized_to_segment",
            "completed",
            f"Sent: {results['sent']}, Failed: {results['failed']}, "
            f"Skipped: {results['skipped']}, Recovered: {results['recovered']}",
        )

        return create_task_result(
            "success",
            {
                "task_type": "send_anonymized_to_segment",
                "results": results,
                "total_processed": sum(results.values()),
            },
        )

    except Exception as e:
        logger.exception("Error in send_anonymized_to_segment")
        return create_task_result("error", error=f"Send task failed: {str(e)}")
