#!/bin/bash
# Entrypoint for scheduler container
# Runs APScheduler for cron-based task scheduling

set -e

echo "════════════════════════════════════════════════════════════════"
echo "  Metrics Service - Task Scheduler"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Configuration:"
echo "  Check Interval: ${SCHEDULER_CHECK_INTERVAL:-60}s"
echo "  Log Level: ${SCHEDULER_LOG_LEVEL:-INFO}"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

# Start task scheduler using Django management command
exec python3.12 manage.py run_task_scheduler \
    --check-interval="${SCHEDULER_CHECK_INTERVAL:-60}" \
    --log-level="${SCHEDULER_LOG_LEVEL:-INFO}"
