"""
Fake hourly collector tasks for testing retries, timeouts, and failures.

Enabled when the TEST_FAKE_TASKS environment variable is set to "true".

Each fake task:
- Sleeps randomly: 50% chance of 10–100s (short), 50% chance of 60s–8 min (long)
- Then randomly succeeds or fails

Timeout behaviour:
- TASK_ABSOLUTE_TIMEOUT_SECONDS (5 min): task is not submitted / not retried if 5 min elapsed since creation
- The long-sleep path (up to 8 min) intentionally exceeds the 5-min absolute timeout — those
  executions will always be killed by dispatcherd and are designed to exercise the timeout/watchdog path.

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

_ABSOLUTE_TIMEOUT_SECONDS = 60 * 5  # TASK_ABSOLUTE_TIMEOUT_SECONDS: max total time from created
_MAX_ATTEMPTS = 10
_RETRY_DELAY_SECONDS = 2
_RETRY_EXPONENT = 1.5

# Cron minutes: every 5 minutes across the full hour
_SCHEDULE = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]


def fake_hourly_collector(**kwargs) -> dict[str, Any]:
    """
    Fake hourly collector for testing.

    50% chance: sleeps 10–100s (short path, can succeed or fail naturally).
    50% chance: sleeps 60s–8 min (long path, always exceeds the 5-min absolute timeout
                and will be killed by dispatcherd — exercises the timeout/watchdog path).
    After sleeping, randomly succeeds or fails with equal probability.
    Designed to exercise retry, failure, and timeout behaviour alongside real collectors.
    """
    task_number = kwargs.get("task_number", "?")
    sleep_seconds = random.randint(10, 100) if random.choice([True, False]) else random.randint(60, 8 * 60)
    will_fail = random.choice([True, False])

    logger.info(
        "Fake_Task_%s: sleeping %ds (absolute=%ds), will_fail=%s",
        task_number,
        sleep_seconds,
        _ABSOLUTE_TIMEOUT_SECONDS,
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
                "TASK_ABSOLUTE_TIMEOUT_SECONDS": _ABSOLUTE_TIMEOUT_SECONDS,
                "retry_delay_seconds": _RETRY_DELAY_SECONDS,
                "retry_exponent": _RETRY_EXPONENT,
            },
            "max_attempts": _MAX_ATTEMPTS,
            "enabled": True,
            "description": f"Fake_Task_{i + 1}: sleeps 10–100s or 1–8 min then randomly succeeds or fails (tests retries/timeouts)",
        }
        for i, minute in enumerate(_SCHEDULE)
    ],
)
