#!/bin/bash
set -e

echo "🚀 Starting metrics-service initialization..."

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
until python manage.py check --database default > /dev/null 2>&1; do
    echo "Database is unavailable - sleeping"
    sleep 2
done
echo "✅ Database is ready!"

# Run database migrations
echo "🔄 Running database migrations..."
python manage.py migrate --noinput

# Initialize service ID if it doesn't exist
echo "🔧 Checking service ID..."
if python manage.py shell -c "
from ansible_base.resource_registry.models import ServiceID
if ServiceID.objects.exists():
    print('ServiceID already exists')
    exit(0)
else:
    print('ServiceID does not exist')
    exit(1)
" > /dev/null 2>&1; then
    echo "✅ ServiceID already exists"
else
    echo "🆔 Initializing service ID..."
    python manage.py init_service_id
    echo "✅ ServiceID initialized"
fi

# Create static directory if it doesn't exist
mkdir -p /app/static

# Collect static files (in production)
if [ "$METRICS_SERVICE_ENV" = "production" ]; then
    echo "📦 Collecting static files..."
    python manage.py collectstatic --noinput
fi

echo "🎉 Initialization complete! Starting Django server..."

# Execute the main command
exec "$@" 