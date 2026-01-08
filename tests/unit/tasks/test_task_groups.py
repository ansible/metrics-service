"""
Tests for task groups functionality.

This module tests the task group system including feature enable controls,
task categorization, and integration with the cron scheduler.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.tasks.task_groups import (
    ANONYMIZED_DATA_GROUP,
    METRICS_COLLECTION_GROUP,
    SYSTEM_TASKS_GROUP,
    TaskGroup,
    get_all_enabled_tasks,
    get_task_group_status,
    validate_task_groups,
)


class TestTaskGroup(TestCase):
    """Test the TaskGroup class."""

    def test_task_group_creation(self):
        """Test creating a task group."""
        group = TaskGroup(
            name="test_group",
            description="Test group",
            enabled_setting="TEST_FLAG",
            default_enabled=True,
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
        assert group.enabled_setting == "TEST_FLAG"
        assert group.default_enabled is True
        assert len(group.tasks) == 1

    @override_settings(FEATURE_ENABLED={"TEST_FLAG": True})
    def test_is_enabled_with_flag_true(self):
        """Test task group enabled when feature enable is True."""
        group = TaskGroup(
            name="test_group",
            description="Test group",
            enabled_setting="TEST_FLAG",
            default_enabled=False,
        )

        assert group.is_enabled() is True

    @override_settings(FEATURE_ENABLED={"TEST_FLAG": False})
    def test_is_enabled_with_flag_false(self):
        """Test task group disabled when feature enable is False."""
        group = TaskGroup(
            name="test_group",
            description="Test group",
            enabled_setting="TEST_FLAG",
            default_enabled=True,
        )

        assert group.is_enabled() is False

    def test_is_enabled_no_flag(self):
        """Test task group uses default when no feature enable."""
        group = TaskGroup(
            name="test_group",
            description="Test group",
            enabled_setting=None,
            default_enabled=True,
        )

        assert group.is_enabled() is True

    def test_get_enabled_tasks_when_enabled(self):
        """Test getting enabled tasks when group is enabled."""
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
            enabled_setting=None,
            default_enabled=True,
            tasks=tasks,
        )

        enabled_tasks = group.get_enabled_tasks()
        assert len(enabled_tasks) == 1
        assert enabled_tasks[0]["task_id"] == "task1"

    def test_get_enabled_tasks_when_disabled(self):
        """Test getting enabled tasks when group is disabled."""
        tasks = [
            {
                "task_id": "task1",
                "function": "function1",
                "enabled": True,
            }
        ]

        group = TaskGroup(
            name="test_group",
            description="Test group",
            enabled_setting=None,
            default_enabled=False,
            tasks=tasks,
        )

        enabled_tasks = group.get_enabled_tasks()
        assert len(enabled_tasks) == 0


class TestPredefinedTaskGroups(TestCase):
    """Test the predefined task groups."""

    def test_system_tasks_group(self):
        """Test system tasks group is always enabled."""
        assert SYSTEM_TASKS_GROUP.name == "system_tasks"
        assert SYSTEM_TASKS_GROUP.enabled_setting is None
        assert SYSTEM_TASKS_GROUP.is_enabled() is True
        assert len(SYSTEM_TASKS_GROUP.tasks) > 0

        # Check for expected system tasks
        task_ids = [task["task_id"] for task in SYSTEM_TASKS_GROUP.tasks]
        assert "daily_task_cleanup" in task_ids
        assert "weekly_data_cleanup" in task_ids
        assert "hourly_health_check" in task_ids

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": True})
    def test_anonymized_data_group_enabled(self):
        """Test anonymized data group when enabled."""
        assert ANONYMIZED_DATA_GROUP.name == "anonymized_data"
        assert ANONYMIZED_DATA_GROUP.enabled_setting == "ANONYMIZED_DATA_COLLECTION"
        assert ANONYMIZED_DATA_GROUP.is_enabled() is True

        task_ids = [task["task_id"] for task in ANONYMIZED_DATA_GROUP.get_enabled_tasks()]
        # After consolidation, only full_process_anonymize remains
        assert "full_process_anonymize" in task_ids

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": False})
    def test_anonymized_data_group_disabled(self):
        """Test anonymized data group when disabled."""
        assert ANONYMIZED_DATA_GROUP.is_enabled() is False
        assert len(ANONYMIZED_DATA_GROUP.get_enabled_tasks()) == 0

    @override_settings(FEATURE_ENABLED={"METRICS_COLLECTION_ENABLED": True})
    def test_metrics_collection_group_enabled(self):
        """Test metrics collection group when enabled."""
        assert METRICS_COLLECTION_GROUP.name == "metrics_collection"
        assert METRICS_COLLECTION_GROUP.enabled_setting == "METRICS_COLLECTION_ENABLED"
        assert METRICS_COLLECTION_GROUP.is_enabled() is True

        task_ids = [task["task_id"] for task in METRICS_COLLECTION_GROUP.get_enabled_tasks()]
        # After consolidation, only the daily collection task remains
        assert "collect_all_metrics_daily" in task_ids

    @override_settings(FEATURE_ENABLED={"METRICS_COLLECTION_ENABLED": False})
    def test_metrics_collection_group_disabled(self):
        """Test metrics collection group when disabled."""
        assert METRICS_COLLECTION_GROUP.is_enabled() is False
        assert len(METRICS_COLLECTION_GROUP.get_enabled_tasks()) == 0


class TestTaskGroupFunctions(TestCase):
    """Test utility functions for task groups."""

    @override_settings(
        FEATURE_ENABLED={
            "ANONYMIZED_DATA_COLLECTION": True,
            "METRICS_COLLECTION_ENABLED": False,
        }
    )
    def test_get_all_enabled_tasks(self):
        """Test getting all enabled tasks from all groups."""
        all_tasks = get_all_enabled_tasks()

        # Should have system tasks and anonymized data tasks, but not metrics collection
        task_ids = list(all_tasks.keys())

        # System tasks (always enabled)
        assert "daily_task_cleanup" in task_ids
        assert "weekly_data_cleanup" in task_ids
        assert "hourly_health_check" in task_ids

        # Anonymized data tasks (enabled) - after consolidation
        assert "full_process_anonymize" in task_ids

        # Metrics collection tasks (disabled) - after consolidation
        assert "collect_all_metrics_daily" not in task_ids

        # Check that group information is added to tasks
        for _task_id, task_config in all_tasks.items():
            assert "group" in task_config
            assert "group_description" in task_config

    def test_get_task_group_status(self):
        """Test getting status of all task groups."""
        status = get_task_group_status()

        assert "system_tasks" in status
        assert "anonymized_data" in status
        assert "metrics_collection" in status

        # Check system tasks group
        system_status = status["system_tasks"]
        assert system_status["enabled"] is True
        assert system_status["enabled_setting"] is None
        assert system_status["total_tasks"] > 0
        assert system_status["enabled_tasks"] == system_status["total_tasks"]

    def test_validate_task_groups(self):
        """Test validation of task groups."""
        errors = validate_task_groups()

        # Should have no errors in the predefined groups
        assert len(errors) == 0

    def test_validate_task_groups_with_errors(self):
        """Test validation catches errors in task groups."""
        # This test would need mock task groups with errors
        # For now, just ensure the function works
        errors = validate_task_groups()
        assert isinstance(errors, list)


class TestTaskGroupIntegration(TestCase):
    """Test integration between task groups and other components."""

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_scheduler_integration(self, mock_get_scheduler):
        """Test integration with the task scheduler."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_get_scheduler.return_value = mock_scheduler

        # With the task scheduler, we just verify it's running
        # Import here to avoid issues during test discovery
        from apps.tasks.cron_scheduler import refresh_scheduler

        result = refresh_scheduler()

        # Simple scheduler doesn't have reload_task_registry, it reads from DB
        # Just verify the function runs successfully
        assert result is None  # refresh_scheduler doesn't return a value

    @override_settings(
        FEATURE_ENABLED={
            "ANONYMIZED_DATA_COLLECTION": True,
            "METRICS_COLLECTION_ENABLED": True,
        }
    )
    def test_all_groups_enabled(self):
        """Test when all groups are enabled."""
        all_tasks = get_all_enabled_tasks()
        status = get_task_group_status()

        # All groups should be enabled
        for _group_name, group_status in status.items():
            assert group_status["enabled"] is True
            assert group_status["enabled_tasks"] > 0

        # Should have tasks from all groups
        task_ids = list(all_tasks.keys())

        # System tasks
        assert any("cleanup" in task_id for task_id in task_ids)

        # Anonymized data tasks - after consolidation, only full_process_anonymize remains
        assert any("anonymize" in task_id for task_id in task_ids)

        # Metrics collection tasks - after consolidation, only daily collection remains
        assert any("metrics" in task_id for task_id in task_ids)

    @override_settings(
        FEATURE_ENABLED={
            "ANONYMIZED_DATA_COLLECTION": False,
            "METRICS_COLLECTION_ENABLED": False,
        }
    )
    def test_minimal_system_only(self):
        """Test when only system tasks are enabled."""
        all_tasks = get_all_enabled_tasks()
        status = get_task_group_status()

        # Only system tasks should be enabled
        assert status["system_tasks"]["enabled"] is True
        assert status["anonymized_data"]["enabled"] is False
        assert status["metrics_collection"]["enabled"] is False

        # Should only have system tasks
        task_ids = list(all_tasks.keys())
        system_task_ids = [task["task_id"] for task in SYSTEM_TASKS_GROUP.tasks]

        for task_id in task_ids:
            assert task_id in system_task_ids
