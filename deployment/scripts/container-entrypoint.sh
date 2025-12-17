#!/bin/bash
#
# Entrypoint script for all-in-one container
# Starts all three services and manages them
#

set -e

# Trap signals for graceful shutdown
trap 'kill -TERM $WEB_PID $DISPATCHER_PID $SCHEDULER_PID 2>/dev/null; wait' SIGTERM SIGINT

echo "========================================="
echo "Metrics Service All-in-One Starting"
echo "========================================="

# Create logs directory
mkdir -p /opt/app-root/src/logs

# Start dispatcher in background
echo "[$(date)] Starting dispatcher..."
python manage.py run_dispatcherd \
    --workers=4 \
    --timeout=3600 \
    --max-tasks=100 \
    --log-level=INFO \
    > /opt/app-root/src/logs/dispatcher.log 2>&1 &
DISPATCHER_PID=$!
echo "[$(date)] Dispatcher started (PID: $DISPATCHER_PID)"

# Start scheduler in background
echo "[$(date)] Starting scheduler..."
python manage.py run_task_scheduler \
    --log-level=INFO \
    --check-interval=60 \
    > /opt/app-root/src/logs/scheduler.log 2>&1 &
SCHEDULER_PID=$!
echo "[$(date)] Scheduler started (PID: $SCHEDULER_PID)"

# Give background processes a moment to start
sleep 2

# Check if background processes are still running
if ! kill -0 $DISPATCHER_PID 2>/dev/null; then
    echo "ERROR: Dispatcher failed to start"
    exit 1
fi

if ! kill -0 $SCHEDULER_PID 2>/dev/null; then
    echo "ERROR: Scheduler failed to start"
    exit 1
fi

# Start web server in foreground (this keeps container alive)
echo "[$(date)] Starting web server..."
echo "========================================="
uwsgi --ini /opt/app-root/etc/uwsgi.ini &
WEB_PID=$!

# Wait for any process to exit
wait -n $WEB_PID $DISPATCHER_PID $SCHEDULER_PID

# If we get here, one process exited - kill the others
echo "[$(date)] A process exited, shutting down all services..."
kill -TERM $WEB_PID $DISPATCHER_PID $SCHEDULER_PID 2>/dev/null || true

# Wait for all processes to terminate
wait

echo "[$(date)] All services stopped"
exit 0
