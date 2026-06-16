"""
Fake hourly collector tasks for testing retries, timeouts, and failures.

Enabled when the TEST_FAKE_TASKS environment variable is set to "true".

Each fake task:
- Sleeps a random duration between 1 and 8 minutes
- Then randomly succeeds or fails

The timeout (7 min) is intentionally shorter than the max sleep (8 min) so that
tasks sleeping beyond 7 minutes are killed by dispatcherd, exercising the timeout path.

Run `manage.py metrics_service init-system-tasks` after setting TEST_FAKE_TASKS=true
to create the tasks in the database.
"""

import logging
import random
import time
from typing import Any

from apps.tasks.task_groups import TaskGroup
from apps.tasks.utils import create_task_result

logger = logging.getLogger(__name__)

# Same settings as real hourly collectors (7 min timeout < 8 min max sleep → tests timeouts)
_TIMEOUT_SECONDS = 60 * 7
_MAX_ATTEMPTS = 5
_RETRY_DELAY_SECONDS = 10

# Cron minutes: every 5 minutes across the full hour
_SCHEDULE = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]


def fake_hourly_collector(**kwargs) -> dict[str, Any]:
    """
    Fake hourly collector for testing.

    Sleeps a random 1–8 minutes, then randomly succeeds or fails.
    Designed to exercise retry, failure, and timeout behaviour alongside real collectors.
    """
    task_number = kwargs.get("task_number", "?")
    sleep_seconds = random.randint(10, 100) if random.choice([True, False]) else random.randint(60, 8 * 60)
    will_fail = random.choice([True, False])

    logger.info(
        "Fake_Task_%s: sleeping %ds (timeout=%ds), will_fail=%s",
        task_number,
        sleep_seconds,
        _TIMEOUT_SECONDS,
        will_fail,
    )

    time.sleep(sleep_seconds)

    if will_fail:
        return create_task_result("error", error=f"Fake_Task_{task_number} randomly failed after {sleep_seconds}s")

    return create_task_result(
        "success",
        data={
            "message": f"Fake_Task_{task_number} completed after {sleep_seconds}s",
            "task_number": task_number,
            "sleep_seconds": sleep_seconds,
        },
    )


FAKE_TASKS_GROUP = TaskGroup(
    name="fake_tasks",
    description="Fake hourly collectors for testing retries, timeouts, and failures (TEST_FAKE_TASKS=true)",
    tasks=[
        {
            "task_id": f"Fake_Task_{i + 1}",
            "function": "fake_hourly_collector",
            "cron": f"{minute} * * * *",
            "args": {
                "task_number": i + 1,
                "TASK_TIMEOUT_SECONDS": _TIMEOUT_SECONDS,
                "TASK_ABSOLUTE_TIMEOUT_SECONDS": _TIMEOUT_SECONDS,
                "retry_delay_seconds": _RETRY_DELAY_SECONDS,
            },
            "max_attempts": _MAX_ATTEMPTS,
            "enabled": True,
            "description": f"Fake_Task_{i + 1}: sleeps 1–8 min then randomly succeeds or fails (tests retries/timeouts)",
        }
        for i, minute in enumerate(_SCHEDULE)
    ],
)
