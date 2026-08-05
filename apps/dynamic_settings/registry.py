"""
Registry of all known settings exposed via the settings API.
"""
from dataclasses import dataclass, field


@dataclass
class SettingDef:
    category: str
    label: str
    description: str
    type: str  # "boolean" | "integer" | "string"
    default: bool | int | str
    requires: list[str] = field(default_factory=list)
    sensitive: bool = False  # when True, GET returns null; the actual value is never echoed back


SETTINGS_REGISTRY: dict[str, SettingDef] = {
    # ------------------------------------------------------------------ collection
    "METRICS_COLLECTION": SettingDef(
        category="collection",
        label="Metrics Collection",
        type="boolean",
        default=True,
        description=(
            "Master gate for all hourly/daily collectors, rollup, and cleanup_metrics_data. "
            "Disable to stop all local scheduled collection."
        ),
    ),
    "UNIFIED_JOBS_COLLECTION": SettingDef(
        category="collection",
        label="Unified Jobs Collector",
        type="boolean",
        default=True,
        requires=["METRICS_COLLECTION"],
        description=(
            "Collect unified jobs (AWX job run records) every hour. "
            "Has no effect when METRICS_COLLECTION is disabled. "
            "Required by CORE_DASHBOARD_COLLECTION."
        ),
    ),
    "JOB_HOST_SUMMARY_COLLECTION": SettingDef(
        category="collection",
        label="Job Host Summary Collector",
        type="boolean",
        default=True,
        requires=["METRICS_COLLECTION"],
        description=(
            "Collect per-host job outcome summaries every hour. "
            "Has no effect when METRICS_COLLECTION is disabled. "
            "Required by CORE_DASHBOARD_COLLECTION."
        ),
    ),
    "CREDENTIALS_COLLECTION": SettingDef(
        category="collection",
        label="Credentials Collector",
        type="boolean",
        default=True,
        requires=["METRICS_COLLECTION"],
        description=(
            "Collect credential-type usage counts every hour. "
            "Has no effect when METRICS_COLLECTION is disabled."
        ),
    ),
    "EVENTS_COLLECTION": SettingDef(
        category="collection",
        label="Job Events Collector",
        type="boolean",
        default=True,
        requires=["METRICS_COLLECTION"],
        description=(
            "Collect event module usage counts every hour (main_jobevent_service). "
            "Disable for high-volume installations where the event table is a concern. "
            "Has no effect when METRICS_COLLECTION is disabled."
        ),
    ),
    "JOBEVENT_ROW_LIMIT": SettingDef(
        category="collection",
        label="Job Event Row Limit",
        type="integer",
        default=200_000,
        requires=["METRICS_COLLECTION", "EVENTS_COLLECTION"],
        description=(
            "Maximum job-event rows fetched per hourly collection run. "
            "At ~800 bytes/row, 200 000 rows ≈ 1.6 GB in memory. "
            "Lower for memory-constrained installations."
        ),
    ),
    "JOBEVENT_JOB_LIMIT": SettingDef(
        category="collection",
        label="Job Event Job Limit",
        type="integer",
        default=1_000,
        requires=["METRICS_COLLECTION", "EVENTS_COLLECTION"],
        description=(
            "Maximum finished jobs processed per hourly window by the events collector. "
            "Limits the SQL IN-clause size. Lower for heavily loaded Controllers."
        ),
    ),
    # ------------------------------------------------------------------ dashboard
    "CORE_DASHBOARD_COLLECTION": SettingDef(
        category="dashboard",
        label="Core Dashboard Collection",
        type="boolean",
        default=True,
        requires=["UNIFIED_JOBS_COLLECTION", "JOB_HOST_SUMMARY_COLLECTION"],
        description=(
            "Sync JobData and JobHostSummary from already-collected hourly metrics. "
            "No additional AWX DB queries. "
            "Requires both UNIFIED_JOBS_COLLECTION and JOB_HOST_SUMMARY_COLLECTION. "
            "Required by DASHBOARD_COLLECTION."
        ),
    ),
    "DASHBOARD_COLLECTION": SettingDef(
        category="dashboard",
        label="Full Dashboard Pipeline",
        type="boolean",
        default=True,
        requires=["CORE_DASHBOARD_COLLECTION"],
        description=(
            "Full automation-reports pipeline: initial backfill of historical job data, "
            "old-data cleanup, and report generation. "
            "Requires CORE_DASHBOARD_COLLECTION."
        ),
    ),
    # ------------------------------------------------------------------ retention
    "HOURLY_RETENTION_DAYS": SettingDef(
        category="retention",
        label="Hourly Collection Retention",
        type="integer",
        default=7,
        description=(
            "Days to keep HourlyMetricsCollection rows. "
            "Older rows are deleted by the daily cleanup_metrics_data task."
        ),
    ),
    "DAILY_RETENTION_DAYS": SettingDef(
        category="retention",
        label="Daily Summary Retention",
        type="integer",
        default=30,
        description=(
            "Days to keep DailyMetricsSummary rows. "
            "Older rows are deleted by the daily cleanup_metrics_data task."
        ),
    ),
    "PAYLOAD_RETENTION_DAYS": SettingDef(
        category="retention",
        label="Sent Payload Retention",
        type="integer",
        default=7,
        description=(
            "Days to keep AnonymizedMetricsPayload rows after successful transmission. "
            "Unsent/failed payloads are always kept for 30 days regardless."
        ),
    ),
    "TASK_RECORD_RETENTION_DAYS": SettingDef(
        category="retention",
        label="Task Record Retention",
        type="integer",
        default=5,
        description=(
            "Days to keep completed and failed Task records. "
            "Recurring task templates are always preserved."
        ),
    ),
    "DASHBOARD_TELEMETRY_RETENTION_DAYS": SettingDef(
        category="retention",
        label="Dashboard Telemetry Retention",
        type="integer",
        default=60,
        description=(
            "Days to keep DashboardTelemetry rows generated by each dashboard collection run."
        ),
    ),
    # ------------------------------------------------------------------ anonymization
    "ANONYMIZED_DATA_COLLECTION": SettingDef(
        category="anonymization",
        label="Anonymized Data Transmission",
        type="boolean",
        default=True,
        requires=["METRICS_COLLECTION"],
        description=(
            "Anonymize daily summaries and transmit to Red Hat via Segment. "
            "Customer opt-out. "
            "Requires METRICS_COLLECTION — needs the daily rollup to have data to transmit."
        ),
    ),
    # ------------------------------------------------------------------ advanced
    "INDIRECT_NODE_COLLECTION": SettingDef(
        category="advanced",
        label="Indirect Node Collection",
        type="boolean",
        default=False,
        description=(
            "Collect indirect managed node audit data daily. "
            "Customer opt-in — disabled by default. "
            "Can also be enabled via the platform AAPFlag FEATURE_INDIRECT_NODE_COLLECTION_ENABLED."
        ),
    ),
}
