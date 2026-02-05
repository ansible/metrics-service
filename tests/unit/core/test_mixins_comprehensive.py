"""
Comprehensive tests for tasks/mixins.py
"""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from apps.tasks.mixins import StatusTrackingMixin

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
        from django.utils import timezone

        from apps.tasks.models import Task

        task = Task.objects.create(name="Test Task", function_name="cleanup_old_data")

        # Set timestamps manually to test get_duration
        task.started_at = timezone.now()
        task.completed_at = timezone.now()
        task.save()

        # Test get_duration
        duration = task.get_duration()
        assert duration is not None
        assert duration >= 0
