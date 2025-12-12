"""
Comprehensive tests for apps/core/utils.py

This module provides extensive test coverage for all utility functions,
including edge cases, error handling, and performance considerations.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from apps.core.models import User
from apps.core.utils import (
    build_error_response,
    get_count_safely,
)
from tests.test_utils import format_task_data, get_related_object_safely, get_system_uuid, get_test_password


@pytest.mark.unit
class TestGetRelatedObjectSafely(TestCase):
    """Test get_related_object_safely utility function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_get_existing_related_object(self):
        """Test getting an existing related object."""
        # Test with a real relationship
        result = get_related_object_safely(self.user, "email")
        assert result == "test@example.com"

    def test_get_nonexistent_related_object_with_default(self):
        """Test getting a nonexistent related object with default value."""
        result = get_related_object_safely(self.user, "nonexistent_field", "default_value")
        assert result == "default_value"

    def test_get_nonexistent_related_object_without_default(self):
        """Test getting a nonexistent related object without default value."""
        result = get_related_object_safely(self.user, "nonexistent_field")
        assert result is None

    def test_get_related_object_from_none_instance(self):
        """Test getting related object from None instance."""
        result = get_related_object_safely(None, "any_field", "default")
        assert result == "default"

    def test_get_related_object_with_nested_attribute(self):
        """Test getting nested attribute access."""
        # This should handle AttributeError gracefully
        result = get_related_object_safely(self.user, "profile.nonexistent", "default")
        assert result == "default"

    def test_get_related_object_with_empty_field_name(self):
        """Test getting related object with empty field name."""
        result = get_related_object_safely(self.user, "", "default")
        assert result == "default"


@pytest.mark.unit
@pytest.mark.django_db
class TestGetCountSafely(TestCase):
    """Test get_count_safely utility function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_get_count_from_queryset(self):
        """Test getting count from queryset."""
        queryset = User.objects.filter(username="testuser")
        result = get_count_safely(queryset)
        assert result == 1

    def test_get_count_from_empty_queryset(self):
        """Test getting count from empty queryset."""
        queryset = User.objects.filter(username="nonexistent")
        result = get_count_safely(queryset)
        assert result == 0

    def test_get_count_from_manager(self):
        """Test getting count from model manager."""
        # Create some test users
        User.objects.create_user(username="user2", password=get_test_password())
        User.objects.create_user(username="user3", password=get_test_password())

        result = get_count_safely(User.objects)
        assert result >= 3  # At least the 3 users we created

    def test_get_count_from_none_object(self):
        """Test getting count from None object."""
        result = get_count_safely(None)
        assert result == 0

    def test_get_count_handles_exception(self):
        """Test that get_count_safely handles exceptions gracefully."""
        mock_queryset = MagicMock()
        mock_queryset.count.side_effect = Exception("Database error")

        result = get_count_safely(mock_queryset)
        assert result == 0


@pytest.mark.unit
class TestBuildErrorResponse(TestCase):
    """Test build_error_response utility function."""

    def test_build_error_response_basic(self):
        """Test building basic error response."""
        result = build_error_response("Test error message")

        assert result["error"] == "Test error message"
        assert result["status_code"] == 400
        assert "timestamp" in result

    def test_build_error_response_with_details(self):
        """Test building error response with details."""
        details = {"field": "username", "issue": "already exists"}
        result = build_error_response("Validation error", details=details)

        assert result["error"] == "Validation error"
        assert result["details"] == details
        assert result["status_code"] == 400

    def test_build_error_response_with_custom_status(self):
        """Test building error response with custom status code."""
        result = build_error_response("Not found", status_code=404)

        assert result["error"] == "Not found"
        assert result["status_code"] == 404

    def test_build_error_response_with_all_parameters(self):
        """Test building error response with all parameters."""
        details = {"validation_errors": ["field1", "field2"]}
        result = build_error_response("Complex error", details=details, status_code=422)

        assert result["error"] == "Complex error"
        assert result["details"] == details
        assert result["status_code"] == 422
        assert "timestamp" in result

    def test_build_error_response_empty_message(self):
        """Test building error response with empty message."""
        result = build_error_response("")

        assert result["error"] == ""
        assert result["status_code"] == 400

    def test_build_error_response_none_details(self):
        """Test building error response with None details."""
        result = build_error_response("Test error", details=None)

        assert result["error"] == "Test error"
        assert "details" not in result or result["details"] is None


@pytest.mark.unit
class TestGetSystemUuid(TestCase):
    """Test get_system_uuid utility function."""

    def test_get_system_uuid_returns_string(self):
        """Test that get_system_uuid returns a string."""
        result = get_system_uuid()
        assert isinstance(result, str)

    def test_get_system_uuid_is_valid_uuid(self):
        """Test that get_system_uuid returns valid UUID."""
        result = get_system_uuid()
        # Should be parseable as UUID
        uuid.UUID(result)

    @patch("django.conf.settings")
    def test_get_system_uuid_consistent(self, mock_settings):
        """Test that get_system_uuid returns consistent value."""
        # Mock settings to return a consistent UUID
        test_uuid = "12345678-1234-5678-1234-567812345678"
        mock_settings.SYSTEM_UUID = test_uuid

        result1 = get_system_uuid()
        result2 = get_system_uuid()
        # Should be consistent when settings has SYSTEM_UUID
        assert result1 == result2
        assert result1 == test_uuid

    def test_get_system_uuid_format(self):
        """Test that get_system_uuid returns properly formatted UUID."""
        result = get_system_uuid()
        # Should be a standard UUID format
        assert len(result) == 36  # Standard UUID length
        assert result.count("-") == 4  # Standard UUID has 4 dashes


@pytest.mark.unit
class TestFormatTaskData(TestCase):
    """Test format_task_data utility function."""

    def test_format_task_data_dict(self):
        """Test formatting dictionary task data."""
        data = {"key": "value", "number": 42}
        result = format_task_data(data)

        assert isinstance(result, str)
        # Should contain the data in some format
        assert "key" in result or "value" in result

    def test_format_task_data_string(self):
        """Test formatting string task data."""
        data = "simple string data"
        result = format_task_data(data)

        assert result == data

    def test_format_task_data_number(self):
        """Test formatting numeric task data."""
        data = 12345
        result = format_task_data(data)

        assert isinstance(result, str)
        assert "12345" in result

    def test_format_task_data_none(self):
        """Test formatting None task data."""
        result = format_task_data(None)

        assert isinstance(result, str)
        # Should handle None gracefully

    def test_format_task_data_complex_object(self):
        """Test formatting complex nested object."""
        data = {
            "users": [{"id": 1, "name": "John"}, {"id": 2, "name": "Jane"}],
            "settings": {"theme": "dark", "notifications": True},
        }
        result = format_task_data(data)

        assert isinstance(result, str)
        # Should contain some representation of the data

    def test_format_task_data_list(self):
        """Test formatting list task data."""
        data = ["item1", "item2", "item3"]
        result = format_task_data(data)

        assert isinstance(result, str)

    def test_format_task_data_boolean(self):
        """Test formatting boolean task data."""
        result_true = format_task_data(True)
        result_false = format_task_data(False)

        assert isinstance(result_true, str)
        assert isinstance(result_false, str)

    def test_format_task_data_empty_dict(self):
        """Test formatting empty dictionary."""
        result = format_task_data({})

        assert isinstance(result, str)

    def test_format_task_data_empty_list(self):
        """Test formatting empty list."""
        result = format_task_data([])

        assert isinstance(result, str)


@pytest.mark.unit
class TestUtilityEdgeCases(TestCase):
    """Test edge cases and error conditions for utility functions."""

    def test_utility_functions_with_unicode(self):
        """Test utility functions with unicode data."""
        unicode_data = {"message": "Hello 世界", "emoji": "🚀"}

        # Should handle unicode without issues
        result = format_task_data(unicode_data)
        assert isinstance(result, str)

    def test_utility_functions_with_large_data(self):
        """Test utility functions with large data structures."""
        large_data = {"data": "x" * 10000}  # 10KB string

        result = format_task_data(large_data)
        assert isinstance(result, str)

    def test_error_response_with_unicode_message(self):
        """Test error response with unicode error message."""
        unicode_message = "Erreur: données invalides 🚫"
        result = build_error_response(unicode_message)

        assert result["error"] == unicode_message
        assert isinstance(result, dict)

    def test_system_uuid_multiple_calls_performance(self):
        """Test system UUID generation performance with multiple calls."""
        import time

        start_time = time.time()
        for _ in range(100):
            get_system_uuid()
        end_time = time.time()

        # Should complete quickly (less than 1 second for 100 calls)
        assert end_time - start_time < 1.0

    def test_utility_functions_thread_safety(self):
        """Test utility functions in concurrent scenarios."""
        import threading

        results = []
        errors = []

        def test_thread():
            try:
                result = get_system_uuid()
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=test_thread) for _ in range(10)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should complete without errors
        assert len(errors) == 0
        assert len(results) == 10

    def test_get_count_safely_with_various_objects(self):
        """Test get_count_safely with various object types."""
        # Test with list (should handle gracefully)
        result = get_count_safely([1, 2, 3])
        assert result == 0  # Lists don't have count() method

        # Test with string (should handle gracefully)
        result = get_count_safely("test string")
        assert result == 0

        # Test with number (should handle gracefully)
        result = get_count_safely(42)
        assert result == 0


@pytest.mark.unit
@pytest.mark.django_db
class TestUtilityIntegrationWithModels(TestCase):
    """Test utility functions integration with Django models."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_get_related_object_with_real_relationships(self):
        """Test get_related_object_safely with real model relationships."""
        # Test accessing related field
        result = get_related_object_safely(self.user, "username")
        assert result == "testuser"

    def test_get_count_safely_with_model_managers(self):
        """Test get_count_safely with various model managers."""
        # Test with User manager
        user_count = get_count_safely(User.objects.all())
        assert user_count >= 1  # At least our test user

    def test_format_task_data_with_model_instances(self):
        """Test format_task_data with Django model instances."""
        # Test with user instance
        result = format_task_data(self.user)
        assert isinstance(result, str)

        # Test with dict containing user data
        user_data = {"user_id": self.user.id, "username": self.user.username}
        result = format_task_data(user_data)
        assert isinstance(result, str)
        assert self.user.username in result or str(self.user.id) in result
