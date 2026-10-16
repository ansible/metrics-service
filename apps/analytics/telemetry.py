"""Record successful analytics endpoint reads in shared database storage."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.analytics.models import AnalyticsUsage

logger = logging.getLogger(__name__)

_DURATION_QUANTUM = Decimal("0.000001")


def record_collector_get(collector: str, duration_ms: float) -> None:
    """Atomically add one successful collector read to its daily database aggregate."""
    try:
        usage_date = timezone.now().date()
        duration = Decimal(str(max(duration_ms, 0))).quantize(_DURATION_QUANTUM)
        with transaction.atomic():
            usage, created = AnalyticsUsage.objects.get_or_create(
                usage_date=usage_date,
                collector=collector,
                defaults={"request_count": 1, "duration_ms_total": duration},
            )
            if not created:
                AnalyticsUsage.objects.filter(pk=usage.pk).update(
                    request_count=F("request_count") + 1,
                    duration_ms_total=F("duration_ms_total") + duration,
                )
    except Exception:
        # Usage statistics must never make a successful API response fail.
        logger.exception("Failed to record analytics usage for %s", collector)


def daily_analytics_usage(summary_date: date) -> dict[str, dict[str, Any]]:
    """Return daily request counts and response-duration statistics by collector."""
    try:
        rows = AnalyticsUsage.objects.filter(usage_date=summary_date).order_by("collector")
        usage = {}
        for row in rows:
            duration_total = float(row.duration_ms_total)
            usage[row.collector] = {
                "request_count": row.request_count,
                "duration_ms_total": duration_total,
                "duration_ms_average": duration_total / row.request_count if row.request_count else None,
            }
        return usage
    except Exception:
        # Telemetry is supplementary; a read issue should not block the daily rollup.
        logger.exception("Failed to aggregate analytics usage for %s", summary_date)
        return {}
