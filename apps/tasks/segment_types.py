"""Typed payload definitions for the anonymized data sent to Segment."""

from typing import TypedDict

from metrics_utility.anonymized_rollups.types import AnonymizedPayload


class SummaryMetadata(TypedDict):
    """Metrics-service metadata added to the utility anonymized payload."""

    summary_date: str
    hourly_collections_count: int
    missing_hours: list[str]
    aggregation_timestamp: str | None
    install_type: str


class DashboardTelemetry(TypedDict):
    """Anonymized dashboard collection performance data."""

    task_name: str | None
    success: bool
    collection_duration_ms: int | float
    number_of_records_processed: int
    database_query_time_ms: int | float | None
    cache_hit_rate: int | float | None


class FinalAnonymizedPayload(AnonymizedPayload):
    """Complete payload persisted by metrics-service and sent to Segment."""

    summary_metadata: SummaryMetadata
    dashboard_telemetry: list[DashboardTelemetry]
