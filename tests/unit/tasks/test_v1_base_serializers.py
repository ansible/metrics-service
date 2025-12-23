"""
Comprehensive tests for tasks/v1/base_serializers.py

This module tests all base serializer classes and mixins used across the API,
including count fields, common serializer functionality, password handling,
and timestamp/status field mixins.
"""

from unittest.mock import Mock, patch

import pytest
from django.test import TestCase
from rest_framework import serializers

from apps.core.models import User
from apps.tasks.models import Task
from apps.tasks.v1.base_serializers import (
    BaseModelSerializer,
    CountFieldMixin,
    PasswordHandlingMixin,
    StatusFieldMixin,
    TimestampFieldMixin,
)
from tests.test_utils import get_test_password

# =============================================================================
# CountFieldMixin Tests
# =============================================================================


@pytest.mark.unit
class TestCountFieldMixin(TestCase):
    """Test CountFieldMixin used across serializers."""

    def setUp(self):
        """Set up test data."""

        class TestSerializer(CountFieldMixin, serializers.Serializer):
            """Test serializer with count field mixin."""

        self.serializer_class = TestSerializer

    def test_get_users_count_with_queryset(self):
        """Test users count with valid queryset."""
        mock_obj = Mock()
        mock_obj.users.count.return_value = 5

        serializer = self.serializer_class()
        count = serializer.get_users_count(mock_obj)

        assert count == 5
        mock_obj.users.count.assert_called_once()

    def test_get_users_count_with_none(self):
        """Test users count returns 0 when users is None."""
        mock_obj = Mock(spec=[])  # No 'users' attribute

        serializer = self.serializer_class()
        count = serializer.get_users_count(mock_obj)

        assert count == 0

    def test_get_admins_count_with_queryset(self):
        """Test admins count with valid queryset."""
        mock_obj = Mock()
        mock_obj.admins.count.return_value = 3

        serializer = self.serializer_class()
        count = serializer.get_admins_count(mock_obj)

        assert count == 3
        mock_obj.admins.count.assert_called_once()

    def test_get_admins_count_with_none(self):
        """Test admins count returns 0 when admins is None."""
        mock_obj = Mock(spec=[])  # No 'admins' attribute

        serializer = self.serializer_class()
        count = serializer.get_admins_count(mock_obj)

        assert count == 0

    def test_get_friends_count_with_queryset(self):
        """Test friends count with valid queryset."""
        mock_obj = Mock()
        mock_obj.people_friends.count.return_value = 10

        serializer = self.serializer_class()
        count = serializer.get_friends_count(mock_obj)

        assert count == 10
        mock_obj.people_friends.count.assert_called_once()

    def test_get_friends_count_with_none(self):
        """Test friends count returns 0 when people_friends is None."""
        mock_obj = Mock(spec=[])  # No 'people_friends' attribute

        serializer = self.serializer_class()
        count = serializer.get_friends_count(mock_obj)

        assert count == 0

    def test_get_tasks_count_with_queryset(self):
        """Test tasks count with valid queryset."""
        mock_obj = Mock()
        mock_obj.tasks.count.return_value = 7

        serializer = self.serializer_class()
        count = serializer.get_tasks_count(mock_obj)

        assert count == 7
        mock_obj.tasks.count.assert_called_once()

    def test_get_tasks_count_with_none(self):
        """Test tasks count returns 0 when tasks is None."""
        mock_obj = Mock(spec=[])  # No 'tasks' attribute

        serializer = self.serializer_class()
        count = serializer.get_tasks_count(mock_obj)

        assert count == 0

    def test_get_executions_count_with_queryset(self):
        """Test executions count with valid queryset."""
        mock_obj = Mock()
        mock_obj.executions.count.return_value = 12

        serializer = self.serializer_class()
        count = serializer.get_executions_count(mock_obj)

        assert count == 12
        mock_obj.executions.count.assert_called_once()

    def test_get_executions_count_with_none(self):
        """Test executions count returns 0 when executions is None."""
        mock_obj = Mock(spec=[])  # No 'executions' attribute

        serializer = self.serializer_class()
        count = serializer.get_executions_count(mock_obj)

        assert count == 0

    def test_count_methods_handle_exceptions(self):
        """Test count methods handle exceptions gracefully."""
        mock_obj = Mock()
        mock_obj.users.count.side_effect = Exception("Database error")

        serializer = self.serializer_class()
        count = serializer.get_users_count(mock_obj)

        # get_count_safely should return 0 on exception
        assert count == 0


# =============================================================================
# BaseModelSerializer Tests
# =============================================================================


@pytest.mark.unit
class TestBaseModelSerializer(TestCase):
    """Test BaseModelSerializer common functionality."""

    def setUp(self):
        """Set up test data."""

        class TestModel:
            """Mock model for testing."""

            id = 1
            name = "Test"
            created = "2024-01-01"
            modified = "2024-01-02"

        class TestSerializer(BaseModelSerializer):
            """Test serializer."""

            class Meta:
                model = TestModel
                fields = ["id", "name", "created", "modified"]

        self.serializer_class = TestSerializer
        self.test_model = TestModel

    def test_setup_common_fields_adds_readonly_fields(self):
        """Test _setup_common_fields adds common read-only fields."""
        serializer = self.serializer_class()

        # Common fields should be marked read-only
        assert hasattr(serializer.Meta, "read_only_fields")
        common_fields = ["id", "url", "created", "modified"]
        for field in common_fields:
            assert field in serializer.Meta.read_only_fields

    def test_setup_common_fields_extends_existing_readonly_fields(self):
        """Test _setup_common_fields extends existing read-only fields."""

        class TestSerializerWithExisting(BaseModelSerializer):
            """Test serializer with existing read-only fields."""

            class Meta:
                model = self.test_model
                fields = ["id", "name"]
                read_only_fields = ["name"]

        serializer = TestSerializerWithExisting()

        # Should include both existing and common read-only fields
        assert "name" in serializer.Meta.read_only_fields
        assert "id" in serializer.Meta.read_only_fields

    def test_validate_calls_super(self):
        """Test validate() calls parent validation."""
        serializer = self.serializer_class()

        attrs = {"name": "Test Name"}
        validated = serializer.validate(attrs)

        # Should return validated attrs
        assert validated == attrs

    def test_to_representation_default_behavior(self):
        """Test to_representation() with default settings."""
        instance = self.test_model()

        # Mock the parent to_representation
        with patch.object(serializers.HyperlinkedModelSerializer, "to_representation") as mock_super:
            mock_super.return_value = {"id": 1, "name": "Test", "value": None}

            serializer = self.serializer_class()
            data = serializer.to_representation(instance)

            # Should include null values by default
            assert "value" in data
            assert data["value"] is None

    def test_to_representation_removes_null_values_when_configured(self):
        """Test to_representation() removes null values when configured."""

        class TestSerializerRemoveNulls(BaseModelSerializer):
            """Test serializer that removes null values."""

            class Meta:
                model = self.test_model
                fields = ["id", "name"]
                remove_null_values = True

        instance = self.test_model()

        # Mock the parent to_representation
        with patch.object(serializers.HyperlinkedModelSerializer, "to_representation") as mock_super:
            mock_super.return_value = {"id": 1, "name": "Test", "value": None}

            serializer = TestSerializerRemoveNulls()
            data = serializer.to_representation(instance)

            # Should exclude null values
            assert "value" not in data
            assert data["id"] == 1
            assert data["name"] == "Test"

    def test_build_common_fields_with_base_fields_only(self):
        """Test build_common_fields() with only base fields."""
        fields = BaseModelSerializer.build_common_fields(["name", "description"])

        expected = ["id", "url", "name", "description", "created", "modified"]
        assert fields == expected

    def test_build_common_fields_with_extra_fields(self):
        """Test build_common_fields() with extra fields."""
        fields = BaseModelSerializer.build_common_fields(["name"], extra_fields=["status", "priority"])

        # Extra fields should be inserted before timestamps
        expected = ["id", "url", "name", "status", "priority", "created", "modified"]
        assert fields == expected

    def test_build_extra_kwargs_basic(self):
        """Test build_extra_kwargs() with view name only."""
        kwargs = BaseModelSerializer.build_extra_kwargs("task-detail")

        assert "url" in kwargs
        assert kwargs["url"]["view_name"] == "task-detail"

    def test_build_extra_kwargs_with_additional_kwargs(self):
        """Test build_extra_kwargs() with additional kwargs."""
        additional = {"name": {"required": True}, "status": {"read_only": True}}
        kwargs = BaseModelSerializer.build_extra_kwargs("task-detail", additional_kwargs=additional)

        assert kwargs["url"]["view_name"] == "task-detail"
        assert kwargs["name"]["required"] is True
        assert kwargs["status"]["read_only"] is True


# =============================================================================
# PasswordHandlingMixin Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestPasswordHandlingMixin(TestCase):
    """Test PasswordHandlingMixin for password hashing."""

    def setUp(self):
        """Set up test data."""

        class TestSerializer(PasswordHandlingMixin, serializers.ModelSerializer):
            """Test serializer with password handling."""

            class Meta:
                model = User
                fields = ["id", "username", "email", "password"]

        self.serializer_class = TestSerializer

    def test_create_with_password(self):
        """Test create() hashes password using set_password()."""
        serializer = self.serializer_class(
            data={"username": "testuser", "email": "test@example.com", "password": "testpass123"}
        )

        assert serializer.is_valid(), serializer.errors

        user = serializer.save()

        # Password should be hashed, not stored as plain text
        assert user.password != "testpass123"
        assert user.check_password("testpass123")

    def test_create_without_password(self):
        """Test create() works without password field."""

        # Make password optional for this test
        class TestSerializerOptionalPassword(PasswordHandlingMixin, serializers.ModelSerializer):
            """Test serializer with optional password."""

            password = serializers.CharField(write_only=True, required=False)

            class Meta:
                model = User
                fields = ["id", "username", "email", "password"]

        serializer = TestSerializerOptionalPassword(data={"username": "testuser2", "email": "test2@example.com"})

        assert serializer.is_valid(), serializer.errors

        user = serializer.save()

        # User should be created even without password
        assert user.username == "testuser2"

    def test_update_with_password(self):
        """Test update() hashes password using set_password()."""
        user = User.objects.create_user(username="olduser", email="old@example.com", password=get_test_password())

        serializer = self.serializer_class(user, data={"username": "olduser", "password": "newpass123"}, partial=True)

        assert serializer.is_valid(), serializer.errors

        updated_user = serializer.save()

        # Password should be updated and hashed
        assert updated_user.check_password("newpass123")
        assert not updated_user.check_password(get_test_password())

    def test_update_without_password(self):
        """Test update() works without changing password."""
        user = User.objects.create_user(username="updateuser", email="update@example.com", password=get_test_password())
        old_password_hash = user.password

        serializer = self.serializer_class(user, data={"email": "newemail@example.com"}, partial=True)

        assert serializer.is_valid(), serializer.errors

        updated_user = serializer.save()

        # Password should remain unchanged
        assert updated_user.password == old_password_hash
        assert updated_user.email == "newemail@example.com"

    def test_create_handles_object_without_set_password(self):
        """Test create() handles objects without set_password method."""

        class SimpleModel:
            """Model without set_password method."""

            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

            def save(self):
                pass

        class SimpleSerializer(PasswordHandlingMixin, serializers.Serializer):
            """Serializer for simple model."""

            name = serializers.CharField()

            def create(self, validated_data):
                return SimpleModel(**validated_data)

        serializer = SimpleSerializer(data={"name": "Test"})
        assert serializer.is_valid()

        # Should not raise error even though object has no set_password
        instance = serializer.save()
        assert instance.name == "Test"


# =============================================================================
# TimestampFieldMixin Tests
# =============================================================================


@pytest.mark.unit
class TestTimestampFieldMixin(TestCase):
    """Test TimestampFieldMixin for timestamp fields."""

    def test_timestamp_fields_are_read_only(self):
        """Test created and modified fields are read-only."""
        # TimestampFieldMixin is a mixin that adds class-level field declarations
        # It's meant to be used with ModelSerializers where fields are declared

        # Verify the mixin defines the fields
        assert hasattr(TimestampFieldMixin, "created")
        assert hasattr(TimestampFieldMixin, "modified")

        # Verify they are DateTimeField instances
        assert isinstance(TimestampFieldMixin.created, serializers.DateTimeField)
        assert isinstance(TimestampFieldMixin.modified, serializers.DateTimeField)

        # Verify they are read-only
        assert TimestampFieldMixin.created.read_only is True
        assert TimestampFieldMixin.modified.read_only is True

    def test_timestamp_fields_have_help_text(self):
        """Test timestamp fields have descriptive help text."""
        # Verify the mixin field definitions include help text
        assert TimestampFieldMixin.created.help_text is not None
        assert TimestampFieldMixin.modified.help_text is not None
        assert "created" in TimestampFieldMixin.created.help_text.lower()
        assert "modified" in TimestampFieldMixin.modified.help_text.lower()


# =============================================================================
# StatusFieldMixin Tests
# =============================================================================


@pytest.mark.unit
class TestStatusFieldMixin(TestCase):
    """Test StatusFieldMixin for status tracking fields."""

    def test_status_fields_are_read_only(self):
        """Test status fields are read-only."""
        # StatusFieldMixin is a mixin that adds class-level field declarations
        # Verify the mixin defines the fields
        assert hasattr(StatusFieldMixin, "started_at")
        assert hasattr(StatusFieldMixin, "completed_at")
        assert hasattr(StatusFieldMixin, "error_message")

        # Verify they are the correct field types
        assert isinstance(StatusFieldMixin.started_at, serializers.DateTimeField)
        assert isinstance(StatusFieldMixin.completed_at, serializers.DateTimeField)
        assert isinstance(StatusFieldMixin.error_message, serializers.CharField)

        # Verify they are read-only
        assert StatusFieldMixin.started_at.read_only is True
        assert StatusFieldMixin.completed_at.read_only is True
        assert StatusFieldMixin.error_message.read_only is True

    def test_status_fields_have_help_text(self):
        """Test status fields have descriptive help text."""
        # Verify the mixin field definitions include help text
        assert StatusFieldMixin.started_at.help_text is not None
        assert StatusFieldMixin.completed_at.help_text is not None
        assert StatusFieldMixin.error_message.help_text is not None

        assert "started" in StatusFieldMixin.started_at.help_text.lower()
        assert "completed" in StatusFieldMixin.completed_at.help_text.lower()
        assert "error" in StatusFieldMixin.error_message.help_text.lower()

    def test_get_duration_with_object_method(self):
        """Test get_duration() calls object's get_duration() method."""

        class TestSerializer(StatusFieldMixin, serializers.Serializer):
            """Test serializer with status fields."""

        mock_obj = Mock()
        mock_obj.get_duration.return_value = 42.5

        serializer = TestSerializer()
        duration = serializer.get_duration(mock_obj)

        assert duration == 42.5
        mock_obj.get_duration.assert_called_once()

    def test_get_duration_without_object_method(self):
        """Test get_duration() returns None for objects without get_duration()."""

        class TestSerializer(StatusFieldMixin, serializers.Serializer):
            """Test serializer with status fields."""

        mock_obj = Mock(spec=[])  # No get_duration method

        serializer = TestSerializer()
        duration = serializer.get_duration(mock_obj)

        assert duration is None


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestBaseSerializerIntegration(TestCase):
    """Integration tests combining multiple mixins."""

    def test_serializer_with_multiple_mixins(self):
        """Test serializer combining multiple mixins."""

        class CombinedSerializer(CountFieldMixin, TimestampFieldMixin, StatusFieldMixin, serializers.ModelSerializer):
            """Serializer with multiple mixins."""

            class Meta:
                model = Task
                fields = ["id", "name", "created", "modified", "started_at", "completed_at"]

        user = User.objects.create_user(username="testuser", email="test@example.com", password=get_test_password())
        task = Task(name="Test Task", function_name="cleanup_old_data", created_by=user)
        task.save()

        serializer = CombinedSerializer(task)

        # All mixin fields should be available
        assert "created" in serializer.fields
        assert "modified" in serializer.fields
        assert "started_at" in serializer.fields
        assert "completed_at" in serializer.fields

        # Count methods should work
        count = serializer.get_tasks_count(task)
        assert count == 0  # No related tasks
