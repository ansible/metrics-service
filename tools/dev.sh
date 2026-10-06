#!/bin/bash
# Dev server script — runs runserver + dispatcherd + scheduler with auto-reload.
# Unlike `metrics_service run` (which uses gunicorn), runserver picks up
# template and code changes without a restart.

set -euo pipefail

cd "$(dirname "$0")/.."

INIT=0
PREFIX=0

usage() {
    echo "Usage: tools/dev.sh [--init] [--prefix]"
    echo "  --init     Run migrations and create the local admin user"
    echo "  --prefix   Expose the API under /api/metrics/v1/"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --init)
            INIT=1
            ;;
        --prefix)
            PREFIX=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if [[ "$PREFIX" -eq 1 ]]; then
    export METRICS_SERVICE_URL_PREFIX="/api/metrics/"
    echo "Using API prefix /api/metrics/ (API URLs: /api/metrics/v1/)"
fi

MANAGE="uv run python manage.py"

if [[ "$INIT" -eq 1 ]]; then
    $MANAGE migrate
    DJANGO_SUPERUSER_PASSWORD=admin $MANAGE createsuperuser --username admin --email admin@example.com --noinput 2>/dev/null || true
    $MANAGE shell -c "
from django.contrib.auth import get_user_model
u = get_user_model().objects.get(username='admin')
u.set_password('admin')
u.save()
"
else
    echo "Hint: run with --init to migrate and create an admin/admin superuser"
fi

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
# `wait -n` requires bash 4.3+; macOS ships with bash 3.2 so fall back to polling.
if [[ "${BASH_VERSINFO[0]}" -gt 4 ]] || [[ "${BASH_VERSINFO[0]}" -eq 4 && "${BASH_VERSINFO[1]}" -ge 3 ]]; then
    wait -n
    code=$?
else
    while kill -0 "${PIDS[@]}" 2>/dev/null; do sleep 1; done
    code=1
fi
echo "A service exited with code $code, shutting down..."
exit "$code"
