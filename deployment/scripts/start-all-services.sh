#!/bin/bash
#
# Start all three services in one container
# This is a simpler alternative to supervisord but less robust
#

set -e

echo "Starting Metrics Service (All-in-One)"
echo "======================================"

# Start dispatcher in background
echo "Starting dispatcher..."
python manage.py run_dispatcherd \
    --workers=4 \
    --timeout=3600 \
    --max-tasks=100 \
    --log-level=INFO &
DISPATCHER_PID=$!

# Start scheduler in background
echo "Starting scheduler..."
python manage.py run_task_scheduler \
    --log-level=INFO \
    --check-interval=60 &
SCHEDULER_PID=$!

# Start web server in foreground (keeps container alive)
echo "Starting web server..."
uwsgi --ini /opt/app-root/etc/uwsgi.ini

# If web server exits, kill background processes
kill $DISPATCHER_PID $SCHEDULER_PID 2>/dev/null || true
