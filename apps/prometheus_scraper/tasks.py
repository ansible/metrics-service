"""
Prometheus scraper tasks.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def scrape_prometheus_endpoints(**kwargs) -> dict[str, Any]:
    """
    Scrape Prometheus metrics endpoints on Controller, EDA, and Hub.

    Authenticates via the gateway WIT mechanism (X-DAB-JW-TOKEN) and calls
    each configured target directly on the internal network.

    Kwargs:
        target_services (list[str] | None): Restrict scraping to these service
            names. Defaults to all configured targets.

    Returns:
        dict: Task result with per-service scrape outcomes.
    """
    from .client import PrometheusScrapeClient

    target_services = kwargs.get("target_services")

    client = PrometheusScrapeClient()
    results = client.scrape_all(target_services=target_services)

    ok = [svc for svc, r in results.items() if r["status"] == "ok"]
    failed = [svc for svc, r in results.items() if r["status"] != "ok"]

    if failed:
        logger.warning("Prometheus scrape: %d failed targets: %s", len(failed), failed)

    # Strip the raw metrics text from the returned task data — it can be
    # megabytes of text and doesn't need to live in the task result store.
    # Log a byte count instead so operators can confirm data was received.
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
