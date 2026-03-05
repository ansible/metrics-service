#!/bin/bash
# Entrypoint for scheduler container
# Runs APScheduler for cron-based task scheduling
# Uses /app/.venv/bin/metrics-service (Dockerfile.dev installs there, not in system PATH).

set -e

METRICS_SERVICE_CLI="${METRICS_SERVICE_CLI:-/app/.venv/bin/metrics-service}"

echo "════════════════════════════════════════════════════════════════"
echo "  Metrics Service - Task Scheduler"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Configuration:"
echo "  Check Interval: ${SCHEDULER_CHECK_INTERVAL:-60}s"
echo "  Log Level: ${SCHEDULER_LOG_LEVEL:-INFO}"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

exec "$METRICS_SERVICE_CLI" scheduler \
    --check-interval="${SCHEDULER_CHECK_INTERVAL:-60}" \
    --log-level="${SCHEDULER_LOG_LEVEL:-INFO}"
