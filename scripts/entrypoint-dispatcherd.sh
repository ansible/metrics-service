#!/bin/bash
# Entrypoint for dispatcherd container
# Runs background task workers

set -e

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

# Start dispatcherd using Django management command
exec python3.12 manage.py run_dispatcherd \
    --workers="${DISPATCHERD_WORKERS:-2}" \
    --timeout="${DISPATCHERD_TIMEOUT:-3600}" \
    --max-tasks="${DISPATCHERD_MAX_TASKS:-100}" \
    --log-level="${DISPATCHERD_LOG_LEVEL:-INFO}"
