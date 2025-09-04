#!/bin/bash
# Startup script for metrics service with automatic dispatcher

# Function to stop background processes on exit
cleanup() {
    echo "Stopping services..."
    kill $DISPATCHER_PID 2>/dev/null
    exit 0
}

# Set trap to cleanup on exit
trap cleanup SIGINT SIGTERM

# Check if we're in a virtual environment or if python is available
if command -v python &> /dev/null; then
    PYTHON_CMD=python
elif command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    echo "Error: Python not found. Please install Python or activate your virtual environment."
    exit 1
fi

# Set default environment variables
export DISPATCHERD_ENABLED=true
export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-metrics_service.settings.development}

echo "Starting metrics service with automatic task dispatcher..."
echo "Django settings: $DJANGO_SETTINGS_MODULE"

# Apply migrations
echo "Applying database migrations..."
$PYTHON_CMD manage.py migrate

# Initialize service ID
echo "Initializing service ID..."
$PYTHON_CMD manage.py init_service_id

# Start dispatcher in background
echo "Starting task dispatcher..."
$PYTHON_CMD manage.py run_dispatcher --workers=2 --timeout=3600 &
DISPATCHER_PID=$!
echo "Task dispatcher started with PID: $DISPATCHER_PID"

# Start web server
echo "Starting web server..."
$PYTHON_CMD manage.py runserver ${HOST:-0.0.0.0}:${PORT:-8000}

# If we get here, the web server has stopped
cleanup