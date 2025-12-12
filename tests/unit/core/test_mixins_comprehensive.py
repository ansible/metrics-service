"""
Comprehensive tests for core/mixins.py
"""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from apps.core.mixins import (
    StatusTrackingMixin,
    TimestampMixin,
)

# ============================================================================
# TimestampMixin Tests
# ============================================================================


class TestTimestampMixin:
    """Test TimestampMixin functionality"""

    def test_timestamp_mixin_is_abstract(self):
        """Test that TimestampMixin is an abstract model"""
        assert TimestampMixin._meta.abstract is True

    def test_timestamp_fields_exist(self):
        """Test that TimestampMixin adds created and modified fields"""
        fields = {field.name for field in TimestampMixin._meta.get_fields()}
        assert "created" in fields
        assert "modified" in fields

    def test_created_field_properties(self):
        """Test created field has correct properties"""
        created_field = TimestampMixin._meta.get_field("created")
        assert created_field.auto_now_add is True
        assert "When this object was created" in created_field.help_text

    def test_modified_field_properties(self):
        """Test modified field has correct properties"""
        modified_field = TimestampMixin._meta.get_field("modified")
        assert modified_field.auto_now is True
        assert "When this object was last modified" in modified_field.help_text


# ============================================================================
# StatusTrackingMixin Tests
# ============================================================================


class TestStatusTrackingMixin:
    """Test StatusTrackingMixin functionality"""

    def test_status_tracking_mixin_is_abstract(self):
        """Test that StatusTrackingMixin is an abstract model"""
        assert StatusTrackingMixin._meta.abstract is True

    def test_status_tracking_fields_exist(self):
        """Test that StatusTrackingMixin adds required fields"""
        fields = {field.name for field in StatusTrackingMixin._meta.get_fields()}
        assert "started_at" in fields
        assert "completed_at" in fields
        assert "error_message" in fields

    def test_mark_started(self):
        """Test mark_started method sets started_at timestamp"""
        instance = Mock(spec=StatusTrackingMixin)
        instance.started_at = None
        instance.save = Mock()

        # Call the actual method
        StatusTrackingMixin.mark_started(instance)

        # Verify started_at was set
        assert instance.started_at is not None
        instance.save.assert_called_once_with(update_fields=["started_at"])

    def test_mark_completed_without_error(self):
        """Test mark_completed method without error message"""
        instance = Mock(spec=StatusTrackingMixin)
        instance.completed_at = None
        instance.error_message = ""
        instance.save = Mock()

        # Call the actual method
        StatusTrackingMixin.mark_completed(instance)

        # Verify completed_at was set
        assert instance.completed_at is not None
        assert instance.error_message == ""
        instance.save.assert_called_once_with(update_fields=["completed_at", "error_message"])

    def test_mark_completed_with_error(self):
        """Test mark_completed method with error message"""
        instance = Mock(spec=StatusTrackingMixin)
        instance.completed_at = None
        instance.error_message = ""
        instance.save = Mock()

        # Call the actual method
        StatusTrackingMixin.mark_completed(instance, error_message="Test error")

        # Verify completed_at was set and error message was stored
        assert instance.completed_at is not None
        assert instance.error_message == "Test error"
        instance.save.assert_called_once_with(update_fields=["completed_at", "error_message"])

    def test_get_duration_with_timestamps(self):
        """Test get_duration calculates correct duration"""
        instance = Mock(spec=StatusTrackingMixin)
        start = timezone.now()
        end = start + timedelta(seconds=10)
        instance.started_at = start
        instance.completed_at = end

        # Call the actual method
        duration = StatusTrackingMixin.get_duration(instance)

        # Verify duration is calculated correctly
        assert duration == 10

    def test_get_duration_without_started_at(self):
        """Test get_duration returns None when started_at is not set"""
        instance = Mock(spec=StatusTrackingMixin)
        instance.started_at = None
        instance.completed_at = timezone.now()

        # Call the actual method
        duration = StatusTrackingMixin.get_duration(instance)

        assert duration is None

    def test_get_duration_without_completed_at(self):
        """Test get_duration returns None when completed_at is not set"""
        instance = Mock(spec=StatusTrackingMixin)
        instance.started_at = timezone.now()
        instance.completed_at = None

        # Call the actual method
        duration = StatusTrackingMixin.get_duration(instance)

        assert duration is None

    def test_get_duration_with_no_timestamps(self):
        """Test get_duration returns None when both timestamps are not set"""
        instance = Mock(spec=StatusTrackingMixin)
        instance.started_at = None
        instance.completed_at = None

        # Call the actual method
        duration = StatusTrackingMixin.get_duration(instance)

        assert duration is None


# ============================================================================
# Integration Tests (Testing mixins with real models)
# ============================================================================


@pytest.mark.django_db
class TestMixinsIntegration:
    """Integration tests for mixins using the Task model"""

    def test_task_uses_status_tracking_mixin(self):
        """Test that Task model properly uses StatusTrackingMixin"""
        from apps.tasks.models import Task

        task = Task.objects.create(name="Test Task", function_name="cleanup_old_data")

        # Test mark_started
        assert task.started_at is None
        task.mark_started()
        task.refresh_from_db()
        assert task.started_at is not None

        # Test mark_completed
        assert task.completed_at is None
        task.mark_completed()
        task.refresh_from_db()
        assert task.completed_at is not None

        # Test get_duration
        duration = task.get_duration()
        assert duration is not None
        assert duration >= 0

    def test_task_mark_completed_with_error(self):
        """Test Task model mark_completed with error message"""
        from apps.tasks.models import Task

        task = Task.objects.create(name="Test Task", function_name="cleanup_old_data")
        task.mark_started()
        task.mark_completed(error_message="Test error")

        task.refresh_from_db()
        assert task.error_message == "Test error"
        assert task.completed_at is not None
