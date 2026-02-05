"""
Comprehensive tests for tasks/mixins.py

This module tests all model mixins used across the task system,
including timestamp tracking and status tracking functionality.
"""

from datetime import timedelta

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.core.models import User
from apps.tasks.mixins import StatusTrackingMixin
from apps.tasks.models import Task
from tests.test_utils import get_test_password

# =============================================================================
# StatusTrackingMixin Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestStatusTrackingMixin(TestCase):
    """Test StatusTrackingMixin for status tracking functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_mixin_is_abstract(self):
        """Test that StatusTrackingMixin is abstract and cannot be instantiated."""
        assert StatusTrackingMixin._meta.abstract is True

    def test_mixin_defines_started_at_field(self):
        """Test that StatusTrackingMixin defines started_at field."""
        assert hasattr(StatusTrackingMixin, "started_at")
        field = StatusTrackingMixin._meta.get_field("started_at")
        assert field.null is True
        assert field.blank is True
        assert "started" in field.help_text.lower()

    def test_mixin_defines_completed_at_field(self):
        """Test that StatusTrackingMixin defines completed_at field."""
        assert hasattr(StatusTrackingMixin, "completed_at")
        field = StatusTrackingMixin._meta.get_field("completed_at")
        assert field.null is True
        assert field.blank is True
        assert "completed" in field.help_text.lower()

    def test_mixin_defines_error_message_field(self):
        """Test that StatusTrackingMixin defines error_message field."""
        assert hasattr(StatusTrackingMixin, "error_message")
        field = StatusTrackingMixin._meta.get_field("error_message")
        assert field.blank is True
        assert "error" in field.help_text.lower()

    def test_get_duration_with_both_timestamps(self):
        """Test get_duration() calculates correct duration."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        # Set timestamps with known difference
        start_time = timezone.now()
        end_time = start_time + timedelta(seconds=42.5)

        task.started_at = start_time
        task.completed_at = end_time
        task.save()

        duration = task.get_duration()

        assert duration is not None
        assert duration == pytest.approx(42.5)

    def test_get_duration_without_started_at(self):
        """Test get_duration() returns None when started_at is missing."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        task.completed_at = timezone.now()
        task.save()

        duration = task.get_duration()

        assert duration is None

    def test_get_duration_without_completed_at(self):
        """Test get_duration() returns None when completed_at is missing."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        task.started_at = timezone.now()
        task.save()

        duration = task.get_duration()

        assert duration is None

    def test_get_duration_without_any_timestamps(self):
        """Test get_duration() returns None when both timestamps are missing."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        duration = task.get_duration()

        assert duration is None


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestMixinIntegration(TestCase):
    """Integration tests for mixins working with real models."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_task_model_uses_status_tracking_mixin(self):
        """Test Task model properly inherits StatusTrackingMixin functionality."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        # StatusTrackingMixin fields should be available
        assert hasattr(task, "started_at")
        assert hasattr(task, "completed_at")
        assert hasattr(task, "error_message")

        # StatusTrackingMixin methods should work
        assert hasattr(task, "get_duration")
