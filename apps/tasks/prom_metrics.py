"""
Custom Prometheus metrics for the metrics-service task subsystem.

Tracks task queue depth by queue name, task execution duration by function,
collector success/failure rate, and Segment payload backlog size.

Metrics are registered once at import time. All functions in this module
are designed to be called from task execution paths without side effects.
"""

from prometheus_client import Counter, Gauge, Histogram

# --- Task queue depth ---
# Gauge: number of tasks currently in "pending" status, labelled by dispatcherd queue name.
# Updated by execute_db_task() on claim and on completion.
TASK_QUEUE_DEPTH = Gauge(
    "metrics_service_task_queue_depth",
    "Number of pending tasks waiting to be executed, by queue name",
    ["queue"],
)

# --- Task execution duration ---
# Histogram: wall-clock seconds from claim to completion, labelled by function name.
TASK_EXECUTION_DURATION_SECONDS = Histogram(
    "metrics_service_task_execution_duration_seconds",
    "Task execution duration in seconds, by function name",
    ["function_name"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
)

# --- Collector success/failure ---
# Counters for collector outcomes, labelled by collector_type and collection_mode.
COLLECTOR_SUCCESS_TOTAL = Counter(
    "metrics_service_collector_success_total",
    "Total number of successful collector runs, by collector_type and collection_mode",
    ["collector_type", "collection_mode"],
)

COLLECTOR_FAILURE_TOTAL = Counter(
    "metrics_service_collector_failure_total",
    "Total number of failed collector runs, by collector_type and collection_mode",
    ["collector_type", "collection_mode"],
)

# --- Segment payload backlog ---
# Gauge: number of AnonymizedMetricsPayload records in pending/retry state.
# Updated at the start of each send_anonymized_to_segment run.
SEGMENT_PAYLOAD_BACKLOG = Gauge(
    "metrics_service_segment_payload_backlog",
    "Number of anonymized metric payloads waiting to be sent to Segment",
)


def refresh_queue_depth_gauge() -> None:
    """
    Refresh TASK_QUEUE_DEPTH for all known dispatcherd queues.

    Reads Task.objects to count pending tasks grouped by function_name, then maps
    each function to its queue via get_queue_for_function(). Safe to call inside
    a worker process — Django ORM must already be set up before calling this.
    """
    import contextlib

    with contextlib.suppress(Exception):
        from django.db.models import Count

        from apps.tasks.models import Task
        from apps.tasks.tasks import get_queue_for_function

        queue_counts: dict[str, int] = {}
        rows = Task.objects.filter(status="pending").values("function_name").annotate(count=Count("id"))
        for row in rows:
            q = get_queue_for_function(row["function_name"])
            queue_counts[q] = queue_counts.get(q, 0) + row["count"]

        # Zero out queues not present in current snapshot so the gauge drops to 0
        # when all tasks in a queue are consumed.
        known_queues = {"metrics", "maintenance", "dashboard"}
        for queue in known_queues | set(queue_counts.keys()):
            TASK_QUEUE_DEPTH.labels(queue=queue).set(queue_counts.get(queue, 0))


def refresh_segment_backlog_gauge() -> None:
    """
    Refresh SEGMENT_PAYLOAD_BACKLOG with the current count of unsent payloads.

    Counts AnonymizedMetricsPayload rows whose status is pending, retry, or
    unavailable (i.e., payloads that have not yet been successfully transmitted).
    Safe to call inside a worker process.
    """
    import contextlib

    with contextlib.suppress(Exception):
        from apps.tasks.models import AnonymizedMetricsPayload

        count = AnonymizedMetricsPayload.objects.filter(status__in=["pending", "retry", "unavailable"]).count()
        SEGMENT_PAYLOAD_BACKLOG.set(count)
