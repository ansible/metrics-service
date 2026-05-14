"""
Settings for the prometheus_scraper app.

Override in deployment settings or via environment variables prefixed with
METRICS_SERVICE_PROMETHEUS_SCRAPER__*, e.g.:
  METRICS_SERVICE_PROMETHEUS_SCRAPER__TARGETS__0__url=http://controller:80/api/controller/v2/metrics
"""

# Targets to scrape. Each entry must have:
#   service  - matches the aap_metrics_target_service WIT claim ("controller", "eda", "hub")
#   url      - full URL to the Prometheus metrics endpoint (direct, not via gateway proxy)
PROMETHEUS_SCRAPER = {
    "TARGETS": [
        {
            "service": "controller",
            "url": "http://localhost:80/api/controller/v2/metrics",
        },
        {
            "service": "eda",
            "url": "http://localhost:8000/api/eda/v1/metrics",
        },
    ],
    # How many seconds before JWT expiry to proactively refresh the token.
    "TOKEN_REFRESH_BUFFER_SECONDS": 60,
    # HTTP request timeout in seconds for each scrape call.
    "SCRAPE_TIMEOUT_SECONDS": 30,
    # Whether to verify TLS certificates when scraping targets.
    "VERIFY_TLS": True,
}
