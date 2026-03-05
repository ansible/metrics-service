#!/bin/bash
# Entrypoint for web container
# Starts Nginx (TLS termination) and Gunicorn (WSGI server)
# Uses /app/.venv when present (Dockerfile.dev); otherwise system Python (production Dockerfile).

set -e

if [ -x "${VENV_GUNICORN:-/app/.venv/bin/gunicorn}" ]; then
    GUNICORN_CMD=("${VENV_GUNICORN:-/app/.venv/bin/gunicorn}")
else
    GUNICORN_CMD=(python3.12 -m gunicorn)
fi

# Function to handle shutdown gracefully
# Optional first argument: exit code to use (default 0 for signal-based graceful shutdown)
shutdown() {
    local exit_code="${1:-0}"
    echo ""
    echo "⚠ Received shutdown signal, stopping services..."

    # Stop Nginx gracefully
    if [ -n "$NGINX_PID" ] && kill -0 "$NGINX_PID" 2>/dev/null; then
        echo "  Stopping Nginx (PID: $NGINX_PID)..."
        nginx -s quit 2>/dev/null || kill -TERM "$NGINX_PID" 2>/dev/null || true
    fi

    # Stop Gunicorn
    if [ -n "$GUNICORN_PID" ] && kill -0 "$GUNICORN_PID" 2>/dev/null; then
        echo "  Stopping Gunicorn (PID: $GUNICORN_PID)..."
        kill -TERM "$GUNICORN_PID" 2>/dev/null || true
        wait "$GUNICORN_PID" 2>/dev/null || true
    fi

    echo "✓ Shutdown complete"
    exit "$exit_code"
}

# Trap signals for graceful shutdown
trap shutdown SIGTERM SIGINT SIGQUIT

echo "════════════════════════════════════════════════════════════════"
echo "  Metrics Service - Web Container"
echo "════════════════════════════════════════════════════════════════"

# Generate TLS certificates if they don't exist
echo ""
echo "─── TLS Certificate Setup ───"
generate-certs.sh

# Start Nginx
echo ""
echo "─── Starting Nginx (TLS Termination) ───"
nginx -t  # Test configuration
nginx     # Start in daemon mode
NGINX_PID=$(cat /var/lib/nginx/nginx.pid 2>/dev/null || pgrep -x nginx | head -1)
if [ -n "$NGINX_PID" ]; then
    echo "✓ Nginx started (PID: $NGINX_PID)"
    echo "  Listening on:"
    echo "    - HTTP:  Port 8080 (redirects to HTTPS)"
    echo "    - HTTPS: Port 8443 (TLS 1.2/1.3)"
else
    echo "✗ Failed to start Nginx"
    exit 1
fi

# Start Gunicorn
echo ""
echo "─── Starting Gunicorn ───"
echo "  Bind: ${GUNICORN_BIND:-127.0.0.1:8000}"
echo "  Workers: ${GUNICORN_WORKERS:-4}"
echo "  Log Level: ${GUNICORN_LOG_LEVEL:-info}"
echo ""

# Start Gunicorn in background so we can monitor both processes
"${GUNICORN_CMD[@]}" metrics_service.wsgi:application \
    --bind "${GUNICORN_BIND:-127.0.0.1:8000}" \
    --workers "${GUNICORN_WORKERS:-4}" \
    --capture-output \
    --access-logfile - \
    --error-logfile - \
    --log-level "${GUNICORN_LOG_LEVEL:-info}" &

GUNICORN_PID=$!

echo "════════════════════════════════════════════════════════════════"
echo "  Web services started successfully"
echo "  Nginx PID: $NGINX_PID"
echo "  Gunicorn PID: $GUNICORN_PID"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Wait for Gunicorn to exit (disable errexit so we always reach shutdown)
set +e
wait "$GUNICORN_PID"
GUNICORN_EXIT_CODE=$?
set -e

echo ""
echo "⚠ Gunicorn exited with code $GUNICORN_EXIT_CODE"

# Stop Nginx when Gunicorn exits (pass through Gunicorn exit code for orchestration)
shutdown "$GUNICORN_EXIT_CODE"
