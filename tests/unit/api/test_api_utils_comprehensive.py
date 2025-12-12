"""
Comprehensive tests for apps/api/utils.py

This module provides extensive test coverage for API utility functions,
including edge cases, error handling, and performance considerations.
"""

from unittest.mock import MagicMock

import pytest
from django.test import TestCase

from apps.api.utils import (
    build_error_response,
    get_count_safely,
)
from apps.core.models import User
from tests.test_utils import get_test_password


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

    def test_error_response_with_unicode_message(self):
        """Test error response with unicode error message."""
        unicode_message = "Erreur: données invalides 🚫"
        result = build_error_response(unicode_message)

        assert result["error"] == unicode_message
        assert isinstance(result, dict)


@pytest.mark.unit
@pytest.mark.django_db
class TestUtilityIntegrationWithModels(TestCase):
    """Test utility functions integration with Django models."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_get_count_safely_with_model_managers(self):
        """Test get_count_safely with various model managers."""
        # Test with User manager
        user_count = get_count_safely(User.objects.all())
        assert user_count >= 1  # At least our test user
