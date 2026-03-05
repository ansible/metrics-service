#!/bin/bash
# Entrypoint for dispatcherd container
# Runs background task workers
# Uses /app/.venv/bin/metrics-service (Dockerfile.dev installs there, not in system PATH).

set -e

METRICS_SERVICE_CLI="${METRICS_SERVICE_CLI:-/app/.venv/bin/metrics-service}"

echo "════════════════════════════════════════════════════════════════"
echo "  Metrics Service - Dispatcherd Worker"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Configuration:"
echo "  Workers: ${DISPATCHERD_WORKERS:-2}"
echo "  Timeout: ${DISPATCHERD_TIMEOUT:-3600}s"
echo "  Max Tasks: ${DISPATCHERD_MAX_TASKS:-100}"
echo "  Log Level: ${DISPATCHERD_LOG_LEVEL:-INFO}"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

exec "$METRICS_SERVICE_CLI" dispatcherd \
    --workers="${DISPATCHERD_WORKERS:-2}" \
    --timeout="${DISPATCHERD_TIMEOUT:-3600}" \
    --max-tasks="${DISPATCHERD_MAX_TASKS:-100}" \
    --log-level="${DISPATCHERD_LOG_LEVEL:-INFO}"
