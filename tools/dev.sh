#!/bin/bash
# Dev server script — runs runserver + dispatcherd + scheduler with auto-reload.
# Unlike `metrics_service run` (which uses gunicorn), runserver picks up
# template and code changes without a restart.

set -euo pipefail

cd "$(dirname "$0")/.."

MANAGE="uv run python manage.py"

# --- init ---
echo SKIPPED: $MANAGE migrate
$MANAGE metrics_service init-service-id
$MANAGE metrics_service init-default-settings
$MANAGE metrics_service init-system-tasks

# --- services ---
PIDS=()

cleanup() {
    echo ""
    echo "Stopping services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    echo "All services stopped."
}

trap cleanup EXIT INT TERM ERR

$MANAGE runserver 0.0.0.0:8000 &
PIDS+=($!)

$MANAGE run_dispatcherd --workers=4 --log-level=DEBUG &
PIDS+=($!)

$MANAGE run_task_scheduler --log-level=DEBUG --check-interval=60 &
PIDS+=($!)

echo "Dev server running (runserver + dispatcherd + scheduler)"
echo "Press Ctrl+C to stop"

# Wait for any child to exit — if one crashes, cleanup trap stops the rest.
wait -n
code=$?
echo "A service exited with code $code, shutting down..."
exit "$code"
