#!/bin/bash
# Entrypoint for scheduler container
# Runs APScheduler for cron-based task scheduling
# Uses /app/.venv when present (Dockerfile.dev); otherwise system Python (production Dockerfile).

set -e

if [ -x "${METRICS_SERVICE_CLI:-/app/.venv/bin/metrics-service}" ]; then
    CLI="${METRICS_SERVICE_CLI:-/app/.venv/bin/metrics-service}"
    RUN_SCHEDULER() { exec "$CLI" scheduler "$@"; }
else
    RUN_SCHEDULER() { exec python3.12 manage.py metrics_service scheduler "$@"; }
fi

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

RUN_SCHEDULER --check-interval="${SCHEDULER_CHECK_INTERVAL:-60}" \
    --log-level="${SCHEDULER_LOG_LEVEL:-INFO}"
