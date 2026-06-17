"""
Unit tests for apps/tasks/collectors/fake_hourly_collectors.py.
"""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# fake_hourly_collector — success path
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_fake_hourly_collector_success():
    """Returns success result when will_fail is False."""
    from apps.tasks.collectors.fake_hourly_collectors import fake_hourly_collector

    # choice([True,False]) → True → short sleep; second choice → False → succeed
    with (
        patch("apps.tasks.collectors.fake_hourly_collectors.time.sleep"),
        patch(
            "apps.tasks.collectors.fake_hourly_collectors.random.choice",
            side_effect=[True, False],
        ),
        patch(
            "apps.tasks.collectors.fake_hourly_collectors.random.randint",
            return_value=20,
        ),
    ):
        result = fake_hourly_collector(task_number=3)

    assert result["status"] == "success"
    assert result["task_number"] == 3
    assert result["sleep_seconds"] == 20
    assert "Fake_Task_3 completed" in result["message"]


# ---------------------------------------------------------------------------
# fake_hourly_collector — failure path
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_fake_hourly_collector_failure():
    """Returns error result when will_fail is True."""
    from apps.tasks.collectors.fake_hourly_collectors import fake_hourly_collector

    # choice → True (short sleep), choice → True (fail)
    with (
        patch("apps.tasks.collectors.fake_hourly_collectors.time.sleep"),
        patch(
            "apps.tasks.collectors.fake_hourly_collectors.random.choice",
            side_effect=[True, True],
        ),
        patch(
            "apps.tasks.collectors.fake_hourly_collectors.random.randint",
            return_value=15,
        ),
    ):
        result = fake_hourly_collector(task_number=7)

    assert result["status"] == "error"
    assert "Fake_Task_7 randomly failed after 15s" in result["error"]


# ---------------------------------------------------------------------------
# fake_hourly_collector — long sleep path
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_fake_hourly_collector_long_sleep_branch():
    """Exercises the long-sleep branch (choice returns False → randint(60, 8*60))."""
    from apps.tasks.collectors.fake_hourly_collectors import fake_hourly_collector

    # First choice → False → long sleep; second choice → False → succeed
    with (
        patch("apps.tasks.collectors.fake_hourly_collectors.time.sleep") as mock_sleep,
        patch(
            "apps.tasks.collectors.fake_hourly_collectors.random.choice",
            side_effect=[False, False],
        ),
        patch(
            "apps.tasks.collectors.fake_hourly_collectors.random.randint",
            return_value=180,
        ),
    ):
        result = fake_hourly_collector(task_number=2)

    mock_sleep.assert_called_once_with(180)
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# fake_hourly_collector — default task_number
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_fake_hourly_collector_default_task_number():
    """task_number defaults to '?' when not provided."""
    from apps.tasks.collectors.fake_hourly_collectors import fake_hourly_collector

    with (
        patch("apps.tasks.collectors.fake_hourly_collectors.time.sleep"),
        patch(
            "apps.tasks.collectors.fake_hourly_collectors.random.choice",
            side_effect=[True, False],
        ),
        patch(
            "apps.tasks.collectors.fake_hourly_collectors.random.randint",
            return_value=10,
        ),
    ):
        result = fake_hourly_collector()

    assert result["status"] == "success"
    assert result["task_number"] == "?"


# ---------------------------------------------------------------------------
# FAKE_TASKS_GROUP — structure
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_fake_tasks_group_has_twelve_tasks():
    from apps.tasks.collectors.fake_hourly_collectors import FAKE_TASKS_GROUP

    assert len(FAKE_TASKS_GROUP.tasks) == 12


@pytest.mark.unit
def test_fake_tasks_group_cron_schedule():
    """Each task fires at a distinct 5-minute interval across the hour."""
    from apps.tasks.collectors.fake_hourly_collectors import FAKE_TASKS_GROUP

    expected_minutes = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
    actual_minutes = [int(t["cron"].split()[0]) for t in FAKE_TASKS_GROUP.tasks]
    assert actual_minutes == expected_minutes


@pytest.mark.unit
def test_fake_tasks_group_timeouts_and_retry():
    """All fake tasks carry the expected absolute timeout, retry delay, and max_attempts."""
    from apps.tasks.collectors.fake_hourly_collectors import (
        _ABSOLUTE_TIMEOUT_SECONDS,
        _MAX_ATTEMPTS,
        _RETRY_DELAY_SECONDS,
        FAKE_TASKS_GROUP,
    )

    for task in FAKE_TASKS_GROUP.tasks:
        assert task["args"]["TASK_ABSOLUTE_TIMEOUT_SECONDS"] == _ABSOLUTE_TIMEOUT_SECONDS
        assert task["args"]["retry_delay_seconds"] == _RETRY_DELAY_SECONDS
        assert task["max_attempts"] == _MAX_ATTEMPTS
        assert "TASK_TIMEOUT_SECONDS" not in task["args"]


@pytest.mark.unit
def test_fake_tasks_group_task_numbers():
    """Each task carries its 1-based task_number."""
    from apps.tasks.collectors.fake_hourly_collectors import FAKE_TASKS_GROUP

    for i, task in enumerate(FAKE_TASKS_GROUP.tasks, start=1):
        assert task["args"]["task_number"] == i
        assert task["task_id"] == f"Fake_Task_{i}"


@pytest.mark.unit
def test_fake_tasks_group_constants():
    """Module constants match expected values."""
    from apps.tasks.collectors import fake_hourly_collectors as m

    assert m._ABSOLUTE_TIMEOUT_SECONDS == 60 * 5
    assert m._MAX_ATTEMPTS == 10
    assert m._RETRY_DELAY_SECONDS == 2
    assert m._RETRY_EXPONENT == 1.5
