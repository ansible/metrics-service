"""Collector task functions for the metrics_collectors queue."""

from .collect_host_metrics_hourly import collect_host_metrics_hourly
from .collect_job_host_summary_hourly import collect_job_host_summary_hourly
from .collect_main_host_hourly import collect_main_host_hourly
from .daily_anonymize_and_prepare import daily_anonymize_and_prepare
from .daily_metrics_rollup import daily_metrics_rollup
from .send_anonymized_to_segment import send_anonymized_to_segment

__all__ = [
    # Hourly collection tasks (MAP phase)
    "collect_job_host_summary_hourly",
    "collect_host_metrics_hourly",
    "collect_main_host_hourly",
    # Daily rollup and anonymization tasks (REDUCE + ANONYMIZE + SEND)
    "daily_metrics_rollup",
    "daily_anonymize_and_prepare",
    "send_anonymized_to_segment",
]
