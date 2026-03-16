#!/bin/bash
# Entrypoint for dispatcherd container
# Runs background task workers
# Uses $HOME/.venv when present (Dockerfile.dev); otherwise system Python (production Dockerfile).

set -e

if [[ -x "${METRICS_SERVICE_CLI:-/var/lib/ansible-automation-platform/metrics/.venv/bin/metrics-service}" ]]; then
    CLI="${METRICS_SERVICE_CLI:-/var/lib/ansible-automation-platform/metrics/.venv/bin/metrics-service}"
    run_dispatcherd() { exec "$CLI" dispatcherd "$@"; }
else
    run_dispatcherd() { exec python3.12 manage.py run_dispatcherd "$@"; }
fi

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

run_dispatcherd --workers="${DISPATCHERD_WORKERS:-2}" \
    --timeout="${DISPATCHERD_TIMEOUT:-3600}" \
    --max-tasks="${DISPATCHERD_MAX_TASKS:-100}" \
    --log-level="${DISPATCHERD_LOG_LEVEL:-INFO}"
