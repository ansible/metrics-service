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
from apps.tasks.mixins import StatusTrackingMixin, TimestampMixin
from apps.tasks.models import Task
from tests.test_utils import get_test_password

# =============================================================================
# TimestampMixin Tests
# =============================================================================


@pytest.mark.unit
class TestTimestampMixin(TestCase):
    """Test TimestampMixin for automatic timestamp tracking."""

    def test_mixin_is_abstract(self):
        """Test that TimestampMixin is abstract and cannot be instantiated."""
        assert TimestampMixin._meta.abstract is True

    def test_mixin_defines_created_field(self):
        """Test that TimestampMixin defines created field."""
        assert hasattr(TimestampMixin, "created")
        field = TimestampMixin._meta.get_field("created")
        assert field.auto_now_add is True
        assert "created" in field.help_text.lower()

    def test_mixin_defines_modified_field(self):
        """Test that TimestampMixin defines modified field."""
        assert hasattr(TimestampMixin, "modified")
        field = TimestampMixin._meta.get_field("modified")
        assert field.auto_now is True
        assert "modified" in field.help_text.lower()

    def test_timestamp_fields_have_help_text(self):
        """Test timestamp fields have descriptive help text."""
        created_field = TimestampMixin._meta.get_field("created")
        modified_field = TimestampMixin._meta.get_field("modified")

        assert "created" in created_field.help_text.lower()
        assert "modified" in modified_field.help_text.lower()


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

    def test_mark_started_sets_timestamp(self):
        """Test mark_started() sets started_at timestamp."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        before = timezone.now()
        task.mark_started()
        after = timezone.now()

        assert task.started_at is not None
        assert before <= task.started_at <= after

    def test_mark_started_persists_to_database(self):
        """Test mark_started() saves to database."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        task.mark_started()

        # Refresh from database
        task.refresh_from_db()

        assert task.started_at is not None

    def test_mark_completed_sets_timestamp(self):
        """Test mark_completed() sets completed_at timestamp."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        before = timezone.now()
        task.mark_completed()
        after = timezone.now()

        assert task.completed_at is not None
        assert before <= task.completed_at <= after

    def test_mark_completed_with_error_message(self):
        """Test mark_completed() sets error message."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        error_msg = "Something went wrong"
        task.mark_completed(error_message=error_msg)

        assert task.completed_at is not None
        assert task.error_message == error_msg

    def test_mark_completed_without_error_message(self):
        """Test mark_completed() with empty error message."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        task.mark_completed()

        assert task.completed_at is not None
        assert task.error_message == ""

    def test_mark_completed_persists_to_database(self):
        """Test mark_completed() saves to database."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        task.mark_completed(error_message="Test error")

        # Refresh from database
        task.refresh_from_db()

        assert task.completed_at is not None
        assert task.error_message == "Test error"

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
        assert hasattr(task, "mark_started")
        assert hasattr(task, "mark_completed")
        assert hasattr(task, "get_duration")

    def test_complete_lifecycle(self):
        """Test complete lifecycle of status tracking."""
        task = Task(name="Lifecycle Test", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        # Initial state
        assert task.started_at is None
        assert task.completed_at is None
        assert task.get_duration() is None

        # Start the process
        task.mark_started()
        assert task.started_at is not None
        assert task.completed_at is None
        assert task.get_duration() is None

        # Small delay
        import time

        time.sleep(0.1)

        # Complete the process
        task.mark_completed()
        assert task.started_at is not None
        assert task.completed_at is not None

        # Duration should be positive
        duration = task.get_duration()
        assert duration is not None
        assert duration > 0
        assert duration >= 0.1  # At least our sleep time

    def test_mark_started_only_updates_started_at_field(self):
        """Test mark_started() only updates started_at field."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        # Set completed_at manually
        original_completed = timezone.now() - timedelta(hours=1)
        task.completed_at = original_completed
        task.save()

        # Call mark_started
        task.mark_started()

        # Refresh from database
        task.refresh_from_db()

        # started_at should be set
        assert task.started_at is not None

        # completed_at should not be changed
        assert task.completed_at == original_completed

    def test_mark_completed_only_updates_relevant_fields(self):
        """Test mark_completed() only updates completed_at and error_message."""
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        # Set started_at manually
        original_started = timezone.now() - timedelta(hours=1)
        task.started_at = original_started
        task.save()

        # Call mark_completed
        task.mark_completed(error_message="Test error")

        # Refresh from database
        task.refresh_from_db()

        # started_at should not be changed
        assert task.started_at == original_started

        # completed_at and error_message should be set
        assert task.completed_at is not None
        assert task.error_message == "Test error"

    def test_status_tracking_with_successful_completion(self):
        """Test status tracking for successful task completion."""
        task = Task(name="Success Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        task.mark_started()
        task.mark_completed()  # No error message = success

        assert task.started_at is not None
        assert task.completed_at is not None
        assert task.error_message == ""
        assert task.get_duration() is not None

    def test_status_tracking_with_failed_completion(self):
        """Test status tracking for failed task completion."""
        task = Task(name="Failed Task", function_name="cleanup_old_data", created_by=self.user)
        task.save()

        task.mark_started()
        task.mark_completed(error_message="Task failed due to timeout")

        assert task.started_at is not None
        assert task.completed_at is not None
        assert task.error_message == "Task failed due to timeout"
        assert task.get_duration() is not None
