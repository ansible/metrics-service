"""
Tests for task groups functionality.

This module tests the task group system including feature enable controls,
task categorization, and integration with the cron scheduler.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.tasks.task_groups import (
    METRICS_COLLECTION_GROUP,
    SYSTEM_TASKS_GROUP,
    TaskGroup,
    get_all_enabled_tasks,
)


class TestTaskGroup(TestCase):
    """Test the TaskGroup class."""

    def test_task_group_creation(self):
        """Test creating a task group."""
        group = TaskGroup(
            name="test_group",
            description="Test group",
            tasks=[
                {
                    "task_id": "test_task",
                    "function": "test_function",
                    "cron": "0 * * * *",
                    "enabled": True,
                    "description": "Test task",
                }
            ],
        )

        assert group.name == "test_group"
        assert group.description == "Test group"
        assert len(group.tasks) == 1

    @override_settings(FEATURE_ENABLED={"TEST_FLAG": True})
    def test_get_enabled_tasks_with_flag_true(self):
        """Test tasks are enabled when group's feature flag is True."""
        group = TaskGroup(
            name="test_group",
            description="Test group",
            feature_flag="TEST_FLAG",
            tasks=[
                {
                    "task_id": "test_task",
                    "function": "test_function",
                    "enabled": True,
                }
            ],
        )

        enabled_tasks = group.get_enabled_tasks()
        assert len(enabled_tasks) == 1

    @override_settings(FEATURE_ENABLED={"TEST_FLAG": False})
    def test_get_enabled_tasks_with_flag_false(self):
        """Test tasks are disabled when group's feature flag is False."""
        group = TaskGroup(
            name="test_group",
            description="Test group",
            feature_flag="TEST_FLAG",
            tasks=[
                {
                    "task_id": "test_task",
                    "function": "test_function",
                    "enabled": True,
                }
            ],
        )

        enabled_tasks = group.get_enabled_tasks()
        assert len(enabled_tasks) == 0

    def test_get_enabled_tasks_no_flag(self):
        """Test groups without feature flags return all enabled tasks."""
        group = TaskGroup(
            name="test_group",
            description="Test group",
            tasks=[
                {
                    "task_id": "test_task",
                    "function": "test_function",
                    "enabled": True,
                }
            ],
        )

        enabled_tasks = group.get_enabled_tasks()
        assert len(enabled_tasks) == 1

    def test_get_enabled_tasks_respects_enabled_field(self):
        """Test getting enabled tasks respects the enabled field."""
        tasks = [
            {
                "task_id": "task1",
                "function": "function1",
                "enabled": True,
            },
            {
                "task_id": "task2",
                "function": "function2",
                "enabled": False,
            },
        ]

        group = TaskGroup(
            name="test_group",
            description="Test group",
            tasks=tasks,
        )

        enabled_tasks = group.get_enabled_tasks()
        assert len(enabled_tasks) == 1
        assert enabled_tasks[0]["task_id"] == "task1"

    @override_settings(FEATURE_ENABLED={"TEST_FLAG": True})
    def test_get_enabled_tasks_with_task_enabled_false(self):
        """Test that individual tasks can be disabled via enabled field."""
        tasks = [
            {
                "task_id": "task1",
                "function": "function1",
                "enabled": True,
            },
            {
                "task_id": "task2",
                "function": "function2",
                "enabled": False,  # Manually disabled
            },
        ]

        group = TaskGroup(
            name="test_group",
            description="Test group",
            feature_flag="TEST_FLAG",
            tasks=tasks,
        )

        enabled_tasks = group.get_enabled_tasks()
        assert len(enabled_tasks) == 1
        assert enabled_tasks[0]["task_id"] == "task1"


class TestPredefinedTaskGroups(TestCase):
    """Test the predefined task groups."""

    def test_system_tasks_group(self):
        """Test system tasks group has no feature flag (always enabled)."""
        assert SYSTEM_TASKS_GROUP.name == "system_tasks"
        assert SYSTEM_TASKS_GROUP.feature_flag is None
        assert len(SYSTEM_TASKS_GROUP.tasks) > 0

        # Check for expected system tasks
        task_ids = [task["task_id"] for task in SYSTEM_TASKS_GROUP.tasks]
        assert "daily_task_cleanup" in task_ids
        assert "hourly_health_check" in task_ids

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": True})
    def test_metrics_collection_group_enabled(self):
        """Test metrics collection group when feature flag is enabled."""
        assert METRICS_COLLECTION_GROUP.name == "metrics_collection"
        assert METRICS_COLLECTION_GROUP.feature_flag == "ANONYMIZED_DATA_COLLECTION"

        task_ids = [task["task_id"] for task in METRICS_COLLECTION_GROUP.get_enabled_tasks()]
        # Should have all tasks when flag is enabled
        assert len(task_ids) > 0
        # Hourly collection tasks
        assert "hourly_job_host_summary" in task_ids
        assert "hourly_unified_jobs" in task_ids
        assert "hourly_credentials" in task_ids
        # Daily snapshot collection
        assert "daily_config" in task_ids
        assert "daily_execution_environments" in task_ids
        # Daily processing tasks
        assert "cleanup_metrics_data" in task_ids
        assert "daily_anonymize" in task_ids
        assert "daily_metrics_rollup" in task_ids
        assert "send_to_segment_daily" in task_ids

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": False})
    def test_metrics_collection_group_disabled(self):
        """Test metrics collection group when feature flag is disabled."""
        enabled_tasks = METRICS_COLLECTION_GROUP.get_enabled_tasks()
        assert len(enabled_tasks) == 0

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": True})
    def test_no_duplicate_cron_slots(self):
        """Assert that no two enabled tasks across all groups share the same cron hour:minute slot.

        Two tasks sharing the same hour and minute may run concurrently, which can cause
        data races (for example, a cleanup task deleting records that a rollup task is
        actively writing). This test prevents that class of scheduling conflict from being
        introduced silently.
        """
        from apps.tasks.task_groups import TASK_GROUPS

        all_enabled_tasks = []
        for group in TASK_GROUPS:
            all_enabled_tasks.extend(group.get_enabled_tasks())

        seen_slots: dict[tuple[int, int], str] = {}
        for task in all_enabled_tasks:
            cron = task.get("cron", "")
            if not cron:
                continue
            parts = cron.split()
            if len(parts) < 2:
                continue
            minute_raw, hour_raw = parts[0], parts[1]
            # Only compare tasks that fire at a single fixed hour:minute.
            if not (minute_raw.isdigit() and hour_raw.isdigit()):
                continue
            minute, hour = int(minute_raw), int(hour_raw)
            slot = (hour, minute)
            task_id = task["task_id"]
            assert slot not in seen_slots, (
                f"Tasks '{task_id}' and '{seen_slots[slot]}' share the same cron slot "
                f"{hour}:{minute:02d} - reschedule one to avoid concurrent execution"
            )
            seen_slots[slot] = task_id


class TestTaskGroupFunctions(TestCase):
    """Test utility functions for task groups."""

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": False})
    def test_get_all_enabled_tasks(self):
        """Test getting all enabled tasks from all groups."""
        all_tasks = get_all_enabled_tasks()

        # Should have only system tasks when metrics collection is disabled
        task_ids = list(all_tasks.keys())

        # System tasks (always enabled)
        assert "daily_task_cleanup" in task_ids
        assert "hourly_health_check" in task_ids

        # Metrics collection tasks (disabled)
        assert "hourly_job_host_summary" not in task_ids
        assert "hourly_host_metrics" not in task_ids
        assert "daily_metrics_rollup" not in task_ids
        assert "daily_anonymize" not in task_ids
        assert "send_to_segment_daily" not in task_ids

        # Check that group information is added to tasks
        for _task_id, task_config in all_tasks.items():
            assert "group" in task_config
            assert "group_description" in task_config


class TestTaskGroupIntegration(TestCase):
    """Test integration between task groups and other components."""

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_scheduler_integration(self, mock_get_scheduler):
        """Test integration with the task scheduler."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_get_scheduler.return_value = mock_scheduler

        # Verify scheduler can be retrieved and is running
        from apps.tasks.cron_scheduler import get_scheduler

        scheduler = get_scheduler()
        assert scheduler == mock_scheduler
        assert scheduler.running is True

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": True})
    def test_all_flags_enabled(self):
        """Test when metrics collection feature flag is enabled."""
        all_tasks = get_all_enabled_tasks()

        # Should have tasks from all groups
        task_ids = list(all_tasks.keys())

        # System tasks
        assert any("cleanup" in task_id for task_id in task_ids)

        # Metrics collection tasks
        assert any("hourly" in task_id for task_id in task_ids)
        assert "daily_metrics_rollup" in task_ids

        # Anonymization tasks
        assert "daily_anonymize" in task_ids
        assert "send_to_segment_daily" in task_ids

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": False})
    def test_minimal_system_only(self):
        """Test when only system tasks are enabled."""
        all_tasks = get_all_enabled_tasks()

        # Only system tasks should be present
        task_ids = list(all_tasks.keys())
        # System tasks should be present
        assert any("cleanup" in task_id for task_id in task_ids)

        # Should only have system tasks
        task_ids = list(all_tasks.keys())
        system_task_ids = [task["task_id"] for task in SYSTEM_TASKS_GROUP.tasks]

        for task_id in task_ids:
            assert task_id in system_task_ids
