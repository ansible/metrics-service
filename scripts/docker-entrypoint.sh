#!/bin/bash
# Docker entrypoint for metrics-service
# Starts Nginx (for TLS termination) and then the main application

set -e

# Function to handle shutdown gracefully
# Optional first argument: exit code to use (default 0 for signal-based graceful shutdown)
shutdown() {
    local exit_code="${1:-0}"
    echo "⚠ Received shutdown signal, stopping services..."

    # Stop Nginx gracefully
    if [ -n "$NGINX_PID" ] && kill -0 "$NGINX_PID" 2>/dev/null; then
        echo "  Stopping Nginx (PID: $NGINX_PID)..."
        nginx -s quit 2>/dev/null || kill -TERM "$NGINX_PID" 2>/dev/null || true
    fi

    # Stop the main application (metrics_service run handles its own process cleanup)
    if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
        echo "  Stopping application (PID: $APP_PID)..."
        kill -TERM "$APP_PID" 2>/dev/null || true
        wait "$APP_PID" 2>/dev/null || true
    fi

    echo "✓ Shutdown complete"
    exit "$exit_code"
}

# Trap signals for graceful shutdown
trap shutdown SIGTERM SIGINT SIGQUIT

echo "════════════════════════════════════════════════════════════════"
echo "  Metrics Service - Production Container"
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
    echo "  Note: Non-privileged ports for rootless operation"
    echo "        In Kubernetes, map 80→8080 and 443→8443 via Service"
else
    echo "✗ Failed to start Nginx"
    exit 1
fi

# Start the main application (metrics_service run)
echo ""
echo "─── Starting Application ───"
echo "Command: $*"
echo ""

# Execute the main command in the background so we can monitor both processes
"$@" &
APP_PID=$!

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  All services started successfully"
echo "  Application PID: $APP_PID"
echo "  Nginx PID: $NGINX_PID"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Wait for the main application to exit
wait "$APP_PID"
APP_EXIT_CODE=$?

echo ""
echo "⚠ Application exited with code $APP_EXIT_CODE"

# Stop Nginx when application exits (pass through app exit code for orchestration)
shutdown "$APP_EXIT_CODE"

