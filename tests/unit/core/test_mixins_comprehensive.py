"""
Comprehensive tests for core/mixins.py
"""

from datetime import timedelta
from unittest.mock import MagicMock, Mock

import pytest
from django.db import models
from django.utils import timezone

from apps.core.mixins import (
    AccessControlMixin,
    StatusTrackingMixin,
    TimestampMixin,
    UserRelatedMixin,
)
from tests.test_utils import get_test_password

# ============================================================================
# Test Models (Concrete implementations for testing abstract mixins)
# ============================================================================


class ConcreteModelWithAccessControl(AccessControlMixin, models.Model):
    """Concrete model for testing AccessControlMixin"""

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "core"


class ConcreteModelWithTimestamp(TimestampMixin):
    """Concrete model for testing TimestampMixin"""

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "core"


class ConcreteModelWithStatusTracking(StatusTrackingMixin):
    """Concrete model for testing StatusTrackingMixin"""

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "core"


class ConcreteModelWithUserRelated(UserRelatedMixin):
    """Concrete model for testing UserRelatedMixin"""

    name = models.CharField(max_length=100)
    users = models.ManyToManyField("core.User", related_name="user_related_test")
    admins = models.ManyToManyField("core.User", related_name="admin_related_test")

    class Meta:
        app_label = "core"


# ============================================================================
# AccessControlMixin Tests
# ============================================================================


class TestAccessControlMixin:
    """Test AccessControlMixin functionality"""

    def test_access_qs_with_default_queryset(self):
        """Test access_qs with default queryset (no queryset parameter)"""
        mock_manager = MagicMock()
        mock_queryset = MagicMock()
        mock_manager.all.return_value = mock_queryset

        # Create a mock class with objects manager
        mock_class = type("MockModel", (AccessControlMixin,), {"objects": mock_manager})

        user = Mock()
        result = mock_class.access_qs(user)

        assert result == mock_queryset
        mock_manager.all.assert_called_once()

    def test_access_qs_with_provided_queryset(self):
        """Test access_qs with explicitly provided queryset"""
        mock_class = type("MockModel", (AccessControlMixin,), {})
        mock_queryset = MagicMock()
        user = Mock()

        result = mock_class.access_qs(user, queryset=mock_queryset)

        assert result == mock_queryset

    def test_access_qs_no_manager_raises_error(self):
        """Test access_qs raises error when model has no objects manager"""
        mock_class = type("MockModel", (AccessControlMixin,), {})
        user = Mock()

        with pytest.raises(AttributeError) as exc_info:
            mock_class.access_qs(user)

        assert "MockModel has no 'objects' manager" in str(exc_info.value)

    def test_access_qs_returns_all_objects(self):
        """Test that access_qs returns all objects (no filtering yet)"""
        mock_manager = MagicMock()
        mock_queryset = MagicMock()
        mock_manager.all.return_value = mock_queryset

        mock_class = type("MockModel", (AccessControlMixin,), {"objects": mock_manager})
        user = Mock()

        result = mock_class.access_qs(user)

        # The method should return the full queryset without filtering
        assert result == mock_queryset


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
# UserRelatedMixin Tests
# ============================================================================


class TestUserRelatedMixin:
    """Test UserRelatedMixin functionality"""

    def test_user_related_mixin_is_abstract(self):
        """Test that UserRelatedMixin is an abstract model"""
        assert UserRelatedMixin._meta.abstract is True

    def test_get_users_count(self):
        """Test get_users_count returns correct count"""
        instance = Mock(spec=UserRelatedMixin)
        mock_users = MagicMock()
        mock_users.count.return_value = 5
        instance.users = mock_users

        # Call the actual method
        count = UserRelatedMixin.get_users_count(instance)

        assert count == 5
        mock_users.count.assert_called_once()

    def test_get_admins_count(self):
        """Test get_admins_count returns correct count"""
        instance = Mock(spec=UserRelatedMixin)
        mock_admins = MagicMock()
        mock_admins.count.return_value = 3
        instance.admins = mock_admins

        # Call the actual method
        count = UserRelatedMixin.get_admins_count(instance)

        assert count == 3
        mock_admins.count.assert_called_once()

    def test_add_user(self):
        """Test add_user adds user to users relationship"""
        instance = Mock(spec=UserRelatedMixin)
        mock_users = MagicMock()
        instance.users = mock_users
        user = Mock()

        # Call the actual method
        UserRelatedMixin.add_user(instance, user)

        mock_users.add.assert_called_once_with(user)

    def test_remove_user(self):
        """Test remove_user removes user from users relationship"""
        instance = Mock(spec=UserRelatedMixin)
        mock_users = MagicMock()
        instance.users = mock_users
        user = Mock()

        # Call the actual method
        UserRelatedMixin.remove_user(instance, user)

        mock_users.remove.assert_called_once_with(user)

    def test_add_admin(self):
        """Test add_admin adds user to admins relationship"""
        instance = Mock(spec=UserRelatedMixin)
        mock_admins = MagicMock()
        instance.admins = mock_admins
        user = Mock()

        # Call the actual method
        UserRelatedMixin.add_admin(instance, user)

        mock_admins.add.assert_called_once_with(user)

    def test_remove_admin(self):
        """Test remove_admin removes user from admins relationship"""
        instance = Mock(spec=UserRelatedMixin)
        mock_admins = MagicMock()
        instance.admins = mock_admins
        user = Mock()

        # Call the actual method
        UserRelatedMixin.remove_admin(instance, user)

        mock_admins.remove.assert_called_once_with(user)


# ============================================================================
# Integration Tests (Testing mixins with real models)
# ============================================================================


@pytest.mark.django_db
class TestMixinsIntegration:
    """Integration tests for mixins using the core models"""

    def test_organization_uses_user_related_mixin(self):
        """Test that Organization model properly uses UserRelatedMixin"""
        from apps.core.models import Organization, User

        org = Organization.objects.create(name="Test Org", description="Test")
        user = User.objects.create_user(username="testuser", password=get_test_password())

        # Test add_user
        org.add_user(user)
        assert org.get_users_count() == 1

        # Test remove_user
        org.remove_user(user)
        assert org.get_users_count() == 0

        # Test add_admin
        org.add_admin(user)
        assert org.get_admins_count() == 1

        # Test remove_admin
        org.remove_admin(user)
        assert org.get_admins_count() == 0

    def test_team_uses_user_related_mixin(self):
        """Test that Team model properly uses UserRelatedMixin"""
        from apps.core.models import Organization, Team, User

        org = Organization.objects.create(name="Test Org", description="Test")
        team = Team.objects.create(name="Test Team", organization=org)
        user = User.objects.create_user(username="testuser2", password=get_test_password())

        # Test add_user
        team.add_user(user)
        assert team.get_users_count() == 1

        # Test add_admin
        team.add_admin(user)
        assert team.get_admins_count() == 1

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

    def test_access_control_mixin_with_user(self):
        """Test AccessControlMixin with User model"""
        from apps.core.models import User

        user = User.objects.create_user(username="testuser3", password=get_test_password())

        # Test access_qs with User model
        queryset = User.access_qs(user)
        assert queryset is not None
        assert queryset.model == User
