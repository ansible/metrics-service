"""
Comprehensive tests for tasks/v1/base_serializers.py

This module tests base serializer classes and mixins used across the API,
including BaseModelSerializer and StatusFieldMixin.
"""

from unittest.mock import Mock

import pytest
from django.test import TestCase
from rest_framework import serializers

from apps.core.models import User
from apps.tasks.models import Task
from apps.tasks.v1.base_serializers import (
    BaseModelSerializer,
    StatusFieldMixin,
)
from tests.test_utils import get_test_password

# =============================================================================
# BaseModelSerializer Tests
# =============================================================================


@pytest.mark.unit
class TestBaseModelSerializer(TestCase):
    """Test BaseModelSerializer common functionality."""

    def test_base_model_serializer_exists(self):
        """Test BaseModelSerializer is a HyperlinkedModelSerializer."""
        # BaseModelSerializer is a simple base class
        assert issubclass(BaseModelSerializer, serializers.HyperlinkedModelSerializer)


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

        assert duration == pytest.approx(42.5)
        mock_obj.get_duration.assert_called_once()


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestBaseSerializerIntegration(TestCase):
    """Integration tests for StatusFieldMixin."""

    def test_serializer_with_status_mixin(self):
        """Test serializer with StatusFieldMixin."""

        class StatusSerializer(StatusFieldMixin, serializers.ModelSerializer):
            """Serializer with status fields."""

            class Meta:
                model = Task
                fields = ["id", "name", "started_at", "completed_at", "error_message"]

        user = User.objects.create_user(username="testuser", email="test@example.com", password=get_test_password())
        task = Task(name="Test Task", function_name="hello_world", created_by=user)
        task.save()

        serializer = StatusSerializer(task)

        # Status mixin fields should be available
        assert "started_at" in serializer.fields
        assert "completed_at" in serializer.fields
        assert "error_message" in serializer.fields
