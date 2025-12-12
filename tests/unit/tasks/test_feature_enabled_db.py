"""
Unit tests for database-driven feature enabled functionality.

Tests the new feature enabled system that stores settings in the database
with fallback to Django settings and defaults.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.tasks.task_groups import (
    disable_task_group,
    enable_task_group,
    get_feature_enabled_from_db,
    get_feature_enabled_status,
    set_feature_enabled,
)
from tests.test_utils import get_test_password

User = get_user_model()


class TestFeatureEnabledDB(TestCase):
    """Test database-driven feature enabled functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_get_feature_enabled_from_db_no_setting(self):
        """Test getting feature enabled when no database setting exists."""
        # Should return default when no setting in DB or Django settings
        result = get_feature_enabled_from_db("NONEXISTENT_SETTING", default=True)
        assert result is True

        result = get_feature_enabled_from_db("NONEXISTENT_SETTING", default=False)
        assert result is False

    @override_settings(FEATURE_ENABLED={"TEST_SETTING": True})
    def test_get_feature_enabled_from_django_settings(self):
        """Test getting feature enabled from Django settings when no DB setting."""
        result = get_feature_enabled_from_db("TEST_SETTING", default=False)
        assert result is True

    def test_get_feature_enabled_from_db_json_value(self):
        """Test getting feature enabled from database with JSON value."""
        from apps.dynamic_settings.models import Setting

        # Create a setting with JSON boolean value
        Setting.objects.create(
            setting_key="JSON_TEST_SETTING", current_value=json.dumps(True), last_modified_by=self.user
        )

        result = get_feature_enabled_from_db("JSON_TEST_SETTING", default=False)
        assert result is True

        # Test with False JSON value
        Setting.objects.filter(setting_key="JSON_TEST_SETTING").update(current_value=json.dumps(False))

        result = get_feature_enabled_from_db("JSON_TEST_SETTING", default=True)
        assert result is False

    def test_get_feature_enabled_from_db_string_value(self):
        """Test getting feature enabled from database with string boolean value."""
        from apps.dynamic_settings.models import Setting

        # Test various string representations of True
        for true_value in ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]:
            Setting.objects.update_or_create(
                setting_key="STRING_TEST_SETTING", defaults={"current_value": true_value, "last_modified_by": self.user}
            )

            result = get_feature_enabled_from_db("STRING_TEST_SETTING", default=False)
            assert result is True, f"Failed for value: {true_value}"

        # Test various string representations of False
        for false_value in ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF"]:
            Setting.objects.update_or_create(
                setting_key="STRING_TEST_SETTING",
                defaults={"current_value": false_value, "last_modified_by": self.user},
            )

            result = get_feature_enabled_from_db("STRING_TEST_SETTING", default=True)
            assert result is False, f"Failed for value: {false_value}"

    def test_get_feature_enabled_from_db_invalid_json(self):
        """Test getting feature enabled when database has invalid JSON."""
        from apps.dynamic_settings.models import Setting

        # Create setting with invalid JSON
        Setting.objects.create(
            setting_key="INVALID_JSON_SETTING", current_value="invalid json {", last_modified_by=self.user
        )

        # Should treat as string boolean and return False (invalid string)
        result = get_feature_enabled_from_db("INVALID_JSON_SETTING", default=True)
        assert result is False

    @patch("apps.tasks.task_groups.logger")
    def test_get_feature_enabled_from_db_exception(self, mock_logger):
        """Test getting feature enabled when database query raises exception."""
        with patch("apps.dynamic_settings.models.Setting.objects.filter", side_effect=Exception("DB Error")):
            result = get_feature_enabled_from_db("ERROR_SETTING", default=True)
            assert result is True
            mock_logger.warning.assert_called_once()

    def test_set_feature_enabled_new_setting(self):
        """Test setting a new feature enabled value."""
        result = set_feature_enabled("NEW_SETTING", True, self.user)
        assert result is True

        # Verify it was saved correctly
        from apps.dynamic_settings.models import Setting

        setting = Setting.objects.get(setting_key="NEW_SETTING")
        assert json.loads(setting.current_value) is True
        assert setting.last_modified_by == self.user

    def test_set_feature_enabled_update_existing(self):
        """Test updating an existing feature enabled value."""
        from apps.dynamic_settings.models import Setting

        # Create initial setting
        Setting.objects.create(
            setting_key="UPDATE_SETTING", current_value=json.dumps(False), last_modified_by=self.user
        )

        # Update it
        result = set_feature_enabled("UPDATE_SETTING", True, self.user)
        assert result is True

        # Verify it was updated
        setting = Setting.objects.get(setting_key="UPDATE_SETTING")
        assert json.loads(setting.current_value) is True
        assert json.loads(setting.previous_value) is False
        assert setting.last_modified_by == self.user

    @patch("apps.tasks.task_groups.logger")
    def test_set_feature_enabled_exception(self, mock_logger):
        """Test setting feature enabled when database operation fails."""
        with patch("apps.dynamic_settings.models.Setting.objects.get_or_create", side_effect=Exception("DB Error")):
            result = set_feature_enabled("ERROR_SETTING", True, self.user)
            assert result is False
            mock_logger.error.assert_called_once()

    def test_enable_task_group_success(self):
        """Test successfully enabling a task group."""
        result = enable_task_group("anonymized_data", self.user)
        assert result is True

        # Verify the setting was created
        from apps.dynamic_settings.models import Setting

        setting = Setting.objects.get(setting_key="ANONYMIZED_DATA_COLLECTION")
        assert json.loads(setting.current_value) is True
        assert setting.last_modified_by == self.user

    def test_enable_task_group_nonexistent(self):
        """Test enabling a nonexistent task group."""
        result = enable_task_group("nonexistent_group", self.user)
        assert result is False

    def test_enable_task_group_no_setting(self):
        """Test enabling a task group that doesn't have an enabled_setting."""
        # System tasks group has no enabled_setting
        result = enable_task_group("system_tasks", self.user)
        assert result is False

    def test_disable_task_group_success(self):
        """Test successfully disabling a task group."""
        result = disable_task_group("metrics_collection", self.user)
        assert result is True

        # Verify the setting was created
        from apps.dynamic_settings.models import Setting

        setting = Setting.objects.get(setting_key="METRICS_COLLECTION_ENABLED")
        assert json.loads(setting.current_value) is False
        assert setting.last_modified_by == self.user

    def test_disable_task_group_system_tasks(self):
        """Test that system tasks group cannot be disabled."""
        result = disable_task_group("system_tasks", self.user)
        assert result is False

    def test_disable_task_group_nonexistent(self):
        """Test disabling a nonexistent task group."""
        result = disable_task_group("nonexistent_group", self.user)
        assert result is False

    @patch("apps.tasks.task_groups.logger")
    def test_enable_task_group_exception(self, mock_logger):
        """Test enabling task group when database operation fails."""
        with patch("apps.dynamic_settings.models.Setting.objects.get_or_create", side_effect=Exception("DB Error")):
            result = enable_task_group("anonymized_data", self.user)
            assert result is False
            mock_logger.error.assert_called_once()

    def test_get_feature_enabled_status_empty(self):
        """Test getting feature enabled status when no database settings exist."""
        status = get_feature_enabled_status()

        # Should have entries for all task group settings
        assert "ANONYMIZED_DATA_COLLECTION" in status
        assert "METRICS_COLLECTION_ENABLED" in status

        # Check that each setting has a source (could be django_settings or default)
        for setting_name in ["ANONYMIZED_DATA_COLLECTION", "METRICS_COLLECTION_ENABLED"]:
            assert "source" in status[setting_name]
            assert status[setting_name]["source"] in ["django_settings", "default"]

    @override_settings(FEATURE_ENABLED={"ANONYMIZED_DATA_COLLECTION": False})
    def test_get_feature_enabled_status_django_settings(self):
        """Test getting feature enabled status from Django settings."""
        status = get_feature_enabled_status()

        setting_status = status["ANONYMIZED_DATA_COLLECTION"]
        assert setting_status["source"] == "django_settings"
        assert setting_status["value"] is False

    def test_get_feature_enabled_status_database(self):
        """Test getting feature enabled status from database."""
        from apps.dynamic_settings.models import Setting

        # Create a database setting
        Setting.objects.create(
            setting_key="ANONYMIZED_DATA_COLLECTION", current_value=json.dumps(True), last_modified_by=self.user
        )

        status = get_feature_enabled_status()

        setting_status = status["ANONYMIZED_DATA_COLLECTION"]
        assert setting_status["source"] == "database"
        assert setting_status["value"] is True
        assert setting_status["last_modified_by"] == "testuser"
        assert "last_modified" in setting_status

    def test_get_feature_enabled_status_invalid_json(self):
        """Test getting feature enabled status with invalid JSON in database."""
        from apps.dynamic_settings.models import Setting

        # Create setting with invalid JSON
        Setting.objects.create(
            setting_key="ANONYMIZED_DATA_COLLECTION", current_value="invalid json", last_modified_by=self.user
        )

        status = get_feature_enabled_status()

        # Should still work, falling back to django settings or default
        assert "ANONYMIZED_DATA_COLLECTION" in status

    @patch("apps.tasks.task_groups.logger")
    def test_get_feature_enabled_status_exception(self, mock_logger):
        """Test getting feature enabled status when database query fails."""
        with patch("apps.dynamic_settings.models.Setting.objects.filter", side_effect=Exception("DB Error")):
            status = get_feature_enabled_status()

            # Should still return status with error fallback
            assert "ANONYMIZED_DATA_COLLECTION" in status
            setting_status = status["ANONYMIZED_DATA_COLLECTION"]
            assert setting_status["source"] == "error_fallback"
            assert "error" in setting_status
            mock_logger.warning.assert_called()


class TestFeatureEnabledIntegration(TestCase):
    """Test integration of feature enabled functionality with task groups."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_task_group_uses_database_setting(self):
        """Test that task groups use database settings when available."""
        from apps.dynamic_settings.models import Setting
        from apps.tasks.task_groups import ANONYMIZED_DATA_GROUP

        # Create database setting that overrides default
        Setting.objects.create(
            setting_key="ANONYMIZED_DATA_COLLECTION",
            current_value=json.dumps(False),  # Override default True
            last_modified_by=self.user,
        )

        # Task group should now be disabled
        assert ANONYMIZED_DATA_GROUP.is_enabled() is False
        assert len(ANONYMIZED_DATA_GROUP.get_enabled_tasks()) == 0

    def test_enable_disable_task_group_integration(self):
        """Test full cycle of enabling and disabling a task group."""
        from apps.tasks.task_groups import METRICS_COLLECTION_GROUP

        # Initially should be disabled (default)
        assert METRICS_COLLECTION_GROUP.is_enabled() is False

        # Enable it
        result = enable_task_group("metrics_collection", self.user)
        assert result is True

        # Should now be enabled
        assert METRICS_COLLECTION_GROUP.is_enabled() is True
        assert len(METRICS_COLLECTION_GROUP.get_enabled_tasks()) > 0

        # Disable it
        result = disable_task_group("metrics_collection", self.user)
        assert result is True

        # Should be disabled again
        assert METRICS_COLLECTION_GROUP.is_enabled() is False
        assert len(METRICS_COLLECTION_GROUP.get_enabled_tasks()) == 0

    def test_feature_enabled_status_with_mixed_sources(self):
        """Test feature enabled status with settings from different sources."""
        from apps.dynamic_settings.models import Setting

        # Create one setting in database
        Setting.objects.create(
            setting_key="ANONYMIZED_DATA_COLLECTION", current_value=json.dumps(True), last_modified_by=self.user
        )

        # Override another in Django settings
        with override_settings(FEATURE_ENABLED={"METRICS_COLLECTION_ENABLED": True}):
            status = get_feature_enabled_status()

            # Database setting
            db_status = status["ANONYMIZED_DATA_COLLECTION"]
            assert db_status["source"] == "database"
            assert db_status["value"] is True

            # Django settings override
            django_status = status["METRICS_COLLECTION_ENABLED"]
            assert django_status["source"] == "django_settings"
            assert django_status["value"] is True


class TestTaskGroupsCoverageCompleteness(TestCase):
    """Additional tests to achieve 100% code coverage for task_groups.py."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_get_task_group_status_with_database_metadata(self):
        """Test get_task_group_status includes database metadata when available."""
        from apps.dynamic_settings.models import Setting
        from apps.tasks.task_groups import get_task_group_status

        # Create a database setting with metadata
        Setting.objects.create(
            setting_key="ANONYMIZED_DATA_COLLECTION", current_value=json.dumps(True), last_modified_by=self.user
        )

        status = get_task_group_status()

        # Check that metadata is included
        anonymized_status = status["anonymized_data"]
        assert "setting_source" in anonymized_status
        assert anonymized_status["setting_source"] == "database"
        assert "setting_last_modified" in anonymized_status
        assert "setting_last_modified_by" in anonymized_status
        assert anonymized_status["setting_last_modified_by"] == "testuser"

    def test_enable_task_group_update_existing_setting(self):
        """Test enable_task_group updates existing setting instead of creating new one."""
        from apps.dynamic_settings.models import Setting

        # Create an existing setting
        Setting.objects.create(
            setting_key="ANONYMIZED_DATA_COLLECTION",
            current_value=json.dumps(False),
            previous_value=json.dumps(True),
            last_modified_by=self.user,
        )

        # Enable the task group (should update existing)
        result = enable_task_group("anonymized_data", self.user)
        assert result is True

        # Verify the setting was updated, not created
        setting = Setting.objects.get(setting_key="ANONYMIZED_DATA_COLLECTION")
        assert json.loads(setting.current_value) is True
        assert json.loads(setting.previous_value) is False  # Previous value was stored
        assert setting.last_modified_by == self.user

    def test_disable_task_group_system_tasks_protection(self):
        """Test that system tasks group cannot be disabled."""
        # System tasks group returns False because it has no enabled_setting
        # This actually happens before the system tasks name check
        result = disable_task_group("system_tasks", self.user)
        assert result is False

        # Verify no setting was created for system tasks
        from apps.dynamic_settings.models import Setting

        assert not Setting.objects.filter(setting_key="SYSTEM_TASKS").exists()

    def test_disable_task_group_system_tasks_name_check(self):
        """Test the system tasks name check by creating a mock system group with enabled_setting."""
        from apps.tasks.task_groups import TASK_GROUPS, TaskGroup

        # Create a mock system_tasks group that has an enabled_setting
        # This allows us to reach the name check at lines 347-348
        mock_system_group = TaskGroup(
            name="system_tasks",
            description="Mock system tasks for testing",
            enabled_setting="MOCK_SYSTEM_SETTING",  # This allows it to pass the first check
            default_enabled=True,
        )

        # Temporarily replace the system tasks group
        original_groups = TASK_GROUPS[:]
        # Find and replace the system tasks group
        for i, group in enumerate(TASK_GROUPS):
            if group.name == "system_tasks":
                TASK_GROUPS[i] = mock_system_group
                break

        try:
            with patch("apps.tasks.task_groups.logger") as mock_logger:
                result = disable_task_group("system_tasks", self.user)
                assert result is False
                # Now the warning should be called
                mock_logger.warning.assert_called_once_with("Cannot disable system tasks group")
        finally:
            # Restore original groups
            TASK_GROUPS[:] = original_groups

    def test_disable_task_group_update_existing_setting(self):
        """Test disable_task_group updates existing setting."""
        from apps.dynamic_settings.models import Setting

        # Create an existing setting
        Setting.objects.create(
            setting_key="METRICS_COLLECTION_ENABLED",
            current_value=json.dumps(True),
            previous_value=json.dumps(False),
            last_modified_by=self.user,
        )

        # Disable the task group
        result = disable_task_group("metrics_collection", self.user)
        assert result is True

        # Verify the setting was updated
        setting = Setting.objects.get(setting_key="METRICS_COLLECTION_ENABLED")
        assert json.loads(setting.current_value) is False
        assert json.loads(setting.previous_value) is True
        assert setting.last_modified_by == self.user

    @patch("apps.tasks.task_groups.logger")
    def test_disable_task_group_exception_handling(self, mock_logger):
        """Test disable_task_group exception handling."""
        with patch("apps.dynamic_settings.models.Setting.objects.get_or_create", side_effect=Exception("DB Error")):
            result = disable_task_group("metrics_collection", self.user)
            assert result is False
            mock_logger.error.assert_called_once()

    def test_get_tasks_by_category(self):
        """Test get_tasks_by_category function."""
        from apps.tasks.task_groups import get_tasks_by_category

        # Get tasks by a known category (maintenance from system tasks)
        maintenance_tasks = get_tasks_by_category("maintenance")
        assert isinstance(maintenance_tasks, list)
        assert len(maintenance_tasks) > 0

        # Should find maintenance tasks
        task_descriptions = [task.get("description", "") for task in maintenance_tasks]
        assert any("cleanup" in desc.lower() for desc in task_descriptions)

        # Test monitoring category
        monitoring_tasks = get_tasks_by_category("monitoring")
        assert isinstance(monitoring_tasks, list)

        # Test with nonexistent category
        empty_tasks = get_tasks_by_category("Nonexistent Category")
        assert empty_tasks == []

    def test_validate_task_id_missing_id(self):
        """Test _validate_task_id with missing task_id."""
        from apps.tasks.task_groups import _validate_task_id

        errors = _validate_task_id(None, "test_group", [])
        assert len(errors) == 1
        assert "missing task_id" in errors[0]

        # Test with empty string
        errors = _validate_task_id("", "test_group", [])
        assert len(errors) == 1
        assert "missing task_id" in errors[0]

    def test_validate_task_id_duplicate(self):
        """Test _validate_task_id with duplicate task_id."""
        from apps.tasks.task_groups import _validate_task_id

        existing_ids = ["task1", "task2", "task3"]
        errors = _validate_task_id("task2", "test_group", existing_ids)
        assert len(errors) == 1
        assert "Duplicate task_id" in errors[0]

    def test_validate_required_fields_missing_fields(self):
        """Test _validate_required_fields with missing required fields."""
        from apps.tasks.task_groups import _validate_required_fields

        # Test with missing function field
        task = {
            "task_id": "test_task",
            "cron": "0 * * * *",
            "description": "Test task",
            # Missing "function"
        }
        errors = _validate_required_fields(task, "test_task")
        assert len(errors) == 1
        assert "missing required field: function" in errors[0]

        # Test with missing multiple fields
        task = {"task_id": "test_task"}  # Missing function, cron, description
        errors = _validate_required_fields(task, "test_task")
        assert len(errors) == 3
        assert any("missing required field: function" in error for error in errors)
        assert any("missing required field: cron" in error for error in errors)
        assert any("missing required field: description" in error for error in errors)

    def test_validate_task_groups_with_actual_errors(self):
        """Test validate_task_groups with a mock task group that has errors."""
        # Create a mock task group with validation errors
        from apps.tasks.task_groups import TASK_GROUPS, TaskGroup, validate_task_groups

        invalid_group = TaskGroup(
            name="invalid_test_group",
            description="Test group with invalid tasks",
            enabled_setting=None,
            default_enabled=True,
            tasks=[
                {
                    # Missing task_id, function, cron, description
                    "enabled": True,
                },
                {
                    "task_id": "duplicate_task",
                    "function": "test_function",
                    "cron": "0 * * * *",
                    "description": "First task",
                    "enabled": True,
                },
                {
                    "task_id": "duplicate_task",  # Duplicate ID
                    "function": "test_function2",
                    "cron": "0 * * * *",
                    "description": "Second task",
                    "enabled": True,
                },
            ],
        )

        # Temporarily add invalid group to TASK_GROUPS
        original_groups = TASK_GROUPS[:]
        TASK_GROUPS.append(invalid_group)

        try:
            errors = validate_task_groups()
            assert len(errors) > 0

            # Check for expected error types
            error_text = " ".join(errors)
            assert "missing task_id" in error_text
            assert "Duplicate task_id" in error_text

        finally:
            # Restore original TASK_GROUPS
            TASK_GROUPS[:] = original_groups
