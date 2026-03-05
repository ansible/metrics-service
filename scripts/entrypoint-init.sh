#!/bin/bash
# Entrypoint for init container
# Runs database migrations and initialization, then exits
# Uses /app/.venv (Dockerfile.dev installs deps there, not system Python).

set -e

VENV_PYTHON="${VENV_PYTHON:-/app/.venv/bin/python}"

echo "════════════════════════════════════════════════════════════════"
echo "  Metrics Service - Database Initialization"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
MAX_RETRIES=30
RETRY_COUNT=0

until "$VENV_PYTHON" -c '
import os
import sys
import psycopg

try:
    conn = psycopg.connect(
        dbname=os.environ.get("METRICS_SERVICE_DATABASES__default__NAME", "metrics_service"),
        user=os.environ.get("METRICS_SERVICE_DATABASES__default__USER", "metrics_service"),
        password=os.environ.get("METRICS_SERVICE_DATABASES__default__PASSWORD", ""),
        host=os.environ.get("METRICS_SERVICE_DATABASES__default__HOST", "postgres"),
        port=os.environ.get("METRICS_SERVICE_DATABASES__default__PORT", "5432"),
    )
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f"Database not ready: {e}")
    sys.exit(1)
' 2>/dev/null; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "✗ Database connection failed after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "  Waiting for database connection... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

echo "✓ Database is ready"
echo ""

# Run database migrations
echo "─── Running Database Migrations ───"
"$VENV_PYTHON" manage.py migrate --noinput
echo "✓ Migrations complete"
echo ""

# Initialize default settings
echo "─── Initializing Default Settings ───"
"$VENV_PYTHON" manage.py metrics_service init-default-settings
echo "✓ Default settings initialized"
echo ""

# Initialize ServiceID for django-ansible-base
echo "─── Initializing ServiceID ───"
"$VENV_PYTHON" manage.py metrics_service init-service-id
echo "✓ ServiceID initialized"
echo ""

# Initialize system tasks
echo "─── Initializing System Tasks ───"
"$VENV_PYTHON" manage.py metrics_service init-system-tasks
echo "✓ System tasks initialized"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "  Database initialization complete"
echo "════════════════════════════════════════════════════════════════"
