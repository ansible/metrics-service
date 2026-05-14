"""
Prometheus scraper tasks.
"""

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


def scrape_prometheus_endpoints(**kwargs) -> dict[str, Any]:
    """
    Scrape Prometheus metrics endpoints on Controller, EDA, and Hub.

    Authenticates via the gateway WIT mechanism (X-DAB-JW-TOKEN) and calls
    each configured target directly on the internal network. Each successful
    scrape is persisted as a PrometheusSnapshot row.

    Kwargs:
        target_services (list[str] | None): Restrict scraping to these service
            names. Defaults to all configured targets.

    Returns:
        dict: Task result with per-service scrape outcomes.
    """
    from .client import PrometheusScrapeClient
    from .models import PrometheusSnapshot

    target_services = kwargs.get("target_services")
    scraped_at = timezone.now()

    client = PrometheusScrapeClient()
    results = client.scrape_all(target_services=target_services)

    snapshots = []
    for svc, result in results.items():
        snapshots.append(
            PrometheusSnapshot(
                service=svc,
                scraped_at=scraped_at,
                status=result["status"],
                http_status=result["http_status"],
                raw_text=result["text"] or "",
                error_message=result["error"] or "",
            )
        )

    if snapshots:
        PrometheusSnapshot.objects.bulk_create(snapshots)
        logger.info("Saved %d PrometheusSnapshot(s) for scrape at %s", len(snapshots), scraped_at)

    ok = [svc for svc, r in results.items() if r["status"] == "ok"]
    failed = [svc for svc, r in results.items() if r["status"] != "ok"]

    if failed:
        logger.warning("Prometheus scrape: %d failed targets: %s", len(failed), failed)

    summary = {
        svc: {
            "status": r["status"],
            "http_status": r["http_status"],
            "bytes": len(r["text"]) if r["text"] else 0,
            "error": r["error"],
        }
        for svc, r in results.items()
    }

    return {
        "status": "success" if not failed else "partial",
        "scraped": ok,
        "failed": failed,
        "results": summary,
    }


def cleanup_prometheus_snapshots(**kwargs) -> dict[str, Any]:
    """
    Delete PrometheusSnapshot rows older than the retention period.

    Kwargs:
        retention_days (int): Rows older than this many days are deleted. Default: 7.
        dry_run (bool): Count rows without deleting. Default: False.

    Returns:
        dict: Task result with deleted (or would-delete) count.
    """
    from .models import PrometheusSnapshot

    retention_days = kwargs.get("retention_days", 7)
    dry_run = kwargs.get("dry_run", False)

    cutoff = timezone.now() - timezone.timedelta(days=retention_days)
    qs = PrometheusSnapshot.objects.filter(scraped_at__lt=cutoff)
    count = qs.count()

    if not dry_run:
        qs.delete()
        logger.info("Deleted %d PrometheusSnapshot(s) older than %d days", count, retention_days)
    else:
        logger.info("Dry run: would delete %d PrometheusSnapshot(s) older than %d days", count, retention_days)

    return {
        "status": "success",
        "deleted" if not dry_run else "would_delete": count,
        "retention_days": retention_days,
        "dry_run": dry_run,
    }
