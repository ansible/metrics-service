#!/bin/bash
set -e

echo "Starting Metrics Service container..."

# Wait for database to be ready
echo "Waiting for database to be ready..."
python -c "
import os, time, psycopg
host = os.environ.get('METRICS_SERVICE_DATABASES__default__HOST', 'postgres')
port = os.environ.get('METRICS_SERVICE_DATABASES__default__PORT', '5432')
user = os.environ.get('METRICS_SERVICE_DATABASES__default__USER', 'metrics_service')
password = os.environ.get('METRICS_SERVICE_DATABASES__default__PASSWORD', 'metrics_service')
db = os.environ.get('METRICS_SERVICE_DATABASES__default__NAME', 'metrics_service')

max_attempts = 30
attempt = 0
while attempt < max_attempts:
    try:
        conn = psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db,
            connect_timeout=5
        )
        conn.close()
        print('✅ Database is ready!')
        break
    except Exception as e:
        attempt += 1
        print(f'⏳ Database not ready yet (attempt {attempt}/{max_attempts}): {e}')
        time.sleep(2)
else:
    print('❌ Database connection failed after all attempts')
    exit(1)
"

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Initialize default settings (puts defaults in the Setting DB table)
echo "Initializing default settings..."
python manage.py metrics_service init-default-settings

# Initialize ServiceID for Django-Ansible-Base
echo "Initializing ServiceID..."
python manage.py metrics_service init-service-id

# Initialize system tasks (puts TASK_GROUPS in the Task DB table)
echo "Initializing system tasks..."
python manage.py metrics_service init-system-tasks

# Collect static files (if needed)
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear || echo "⚠️ Static files collection failed (continuing...)"

# Create logs directory if it doesn't exist (ignore permission errors for bind mounts)
mkdir -p /app/logs 2>/dev/null || true

echo "Initialization complete! Starting application..."

# Execute the command passed to the container
exec "$@"
