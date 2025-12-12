"""
Tests for core utility functions to achieve 100% code coverage.
"""

import logging
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from apps.core.utils import (
    build_error_response,
    get_count_safely,
)
from tests.test_utils import get_related_object_safely


@pytest.mark.unit
class CoreUtilsTestCase(TestCase):
    """Test cases for core utility functions."""

    def test_get_related_object_safely_success(self):
        """Test successful retrieval of related object."""
        # Create a mock instance with a related field
        mock_instance = Mock()
        mock_related_object = Mock()
        mock_instance.related_field = mock_related_object

        result = get_related_object_safely(mock_instance, "related_field")

        self.assertEqual(result, mock_related_object)

    def test_get_related_object_safely_attribute_error(self):
        """Test handling of AttributeError."""
        mock_instance = Mock()
        # Configure mock to raise AttributeError when accessing the field
        mock_instance.configure_mock(nonexistent_field=Mock(side_effect=AttributeError))
        del mock_instance.nonexistent_field  # Remove the attribute completely

        result = get_related_object_safely(mock_instance, "nonexistent_field", default="default_value")

        self.assertEqual(result, "default_value")

    def test_get_related_object_safely_does_not_exist_exception(self):
        """Test handling of DoesNotExist exception."""
        # Create a mock instance with a DoesNotExist exception class
        mock_instance = Mock()
        mock_instance.DoesNotExist = type("DoesNotExist", (Exception,), {})

        # Create a property that raises DoesNotExist when accessed
        def raise_does_not_exist():
            raise mock_instance.DoesNotExist("Related object does not exist")

        # Use property to simulate the field access raising DoesNotExist
        type(mock_instance).related_field = property(lambda self: raise_does_not_exist())

        result = get_related_object_safely(mock_instance, "related_field", default="fallback")

        self.assertEqual(result, "fallback")

    def test_get_related_object_safely_default_none(self):
        """Test default value when none provided."""
        mock_instance = Mock()
        del mock_instance.nonexistent_field

        result = get_related_object_safely(mock_instance, "nonexistent_field")

        self.assertIsNone(result)

    def test_get_related_object_safely_with_custom_default(self):
        """Test with custom default value."""
        mock_instance = Mock()
        del mock_instance.missing_field
        custom_default = {"custom": "default"}

        result = get_related_object_safely(mock_instance, "missing_field", default=custom_default)

        self.assertEqual(result, custom_default)

    def test_get_count_safely_success(self):
        """Test successful count retrieval."""
        mock_queryset = Mock()
        mock_queryset.count.return_value = 5

        result = get_count_safely(mock_queryset)

        self.assertEqual(result, 5)
        mock_queryset.count.assert_called_once()

    def test_get_count_safely_exception(self):
        """Test handling of exception during count."""
        mock_queryset = Mock()
        mock_queryset.count.side_effect = Exception("Database error")

        with patch("apps.core.utils.logger") as mock_logger:
            result = get_count_safely(mock_queryset)

        self.assertEqual(result, 0)
        mock_logger.warning.assert_called_once()
        self.assertIn("Error getting count", mock_logger.warning.call_args[0][0])

    def test_get_count_safely_type_conversion(self):
        """Test type conversion of count result."""
        mock_queryset = Mock()
        mock_queryset.count.return_value = "10"  # String instead of int

        result = get_count_safely(mock_queryset)

        self.assertEqual(result, 10)
        self.assertIsInstance(result, int)

    def test_get_count_safely_zero_count(self):
        """Test handling of zero count."""
        mock_queryset = Mock()
        mock_queryset.count.return_value = 0

        result = get_count_safely(mock_queryset)

        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)

    def test_get_count_safely_large_count(self):
        """Test handling of large count values."""
        mock_queryset = Mock()
        mock_queryset.count.return_value = 999999

        result = get_count_safely(mock_queryset)

        self.assertEqual(result, 999999)
        self.assertIsInstance(result, int)

    @patch("apps.core.utils.timezone")
    def test_build_error_response_basic(self, mock_timezone):
        """Test basic error response building."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        result = build_error_response("Test error message")

        expected = {
            "error": "Test error message",
            "status_code": 400,
            "timestamp": "2023-01-01T12:00:00",
        }
        self.assertEqual(result, expected)
        mock_timezone.now.assert_called_once()
        mock_now.isoformat.assert_called_once()

    @patch("apps.core.utils.timezone")
    def test_build_error_response_with_details(self, mock_timezone):
        """Test error response building with details."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        details = {"field": "username", "code": "invalid"}
        result = build_error_response("Validation error", details=details, status_code=422)

        expected = {
            "error": "Validation error",
            "status_code": 422,
            "timestamp": "2023-01-01T12:00:00",
            "details": {"field": "username", "code": "invalid"},
        }
        self.assertEqual(result, expected)

    @patch("apps.core.utils.timezone")
    def test_build_error_response_custom_status_code(self, mock_timezone):
        """Test error response with custom status code."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        result = build_error_response("Server error", status_code=500)

        self.assertEqual(result["status_code"], 500)
        self.assertEqual(result["error"], "Server error")
        self.assertEqual(result["timestamp"], "2023-01-01T12:00:00")

    @patch("apps.core.utils.timezone")
    def test_build_error_response_empty_details(self, mock_timezone):
        """Test error response with empty details dictionary."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        result = build_error_response("Test error", details={})

        # Empty details dictionary is falsy, so it should not be included
        self.assertNotIn("details", result)

    @patch("apps.core.utils.timezone")
    def test_build_error_response_truthy_details(self, mock_timezone):
        """Test error response with truthy details to ensure 'if details' branch."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        # Test with truthy non-empty details
        result = build_error_response("Test error", details={"key": "value"})

        # Non-empty details should be included
        self.assertIn("details", result)
        self.assertEqual(result["details"], {"key": "value"})

    @patch("apps.core.utils.timezone")
    def test_build_error_response_none_details(self, mock_timezone):
        """Test error response with None details."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        result = build_error_response("Test error", details=None)

        # None details should not be included
        self.assertNotIn("details", result)
        expected_keys = {"error", "status_code", "timestamp"}
        self.assertEqual(set(result.keys()), expected_keys)

    @patch("apps.core.utils.timezone")
    def test_build_error_response_complex_details(self, mock_timezone):
        """Test error response with complex details structure."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        complex_details = {
            "errors": [{"field": "email", "message": "Invalid format"}, {"field": "password", "message": "Too short"}],
            "meta": {"request_id": "abc123"},
        }
        result = build_error_response("Multiple validation errors", details=complex_details)

        self.assertEqual(result["details"], complex_details)

    @patch("apps.core.utils.timezone")
    def test_build_error_response_default_parameters(self, mock_timezone):
        """Test error response with only required parameters."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        result = build_error_response("Minimal error")

        expected = {
            "error": "Minimal error",
            "status_code": 400,  # Default status code
            "timestamp": "2023-01-01T12:00:00",
        }
        self.assertEqual(result, expected)
        # Should not have details key when None
        self.assertNotIn("details", result)

    @patch("apps.core.utils.timezone")
    def test_build_error_response_different_status_codes(self, mock_timezone):
        """Test error response with various status codes."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        status_codes = [400, 401, 403, 404, 422, 500, 503]

        for status_code in status_codes:
            with self.subTest(status_code=status_code):
                result = build_error_response("Test error", status_code=status_code)
                self.assertEqual(result["status_code"], status_code)

    def test_logger_configuration(self):
        """Test that logger is properly configured."""
        from apps.core.utils import logger

        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "apps.core.utils")

    def test_get_related_object_safely_various_exception_types(self):
        """Test handling of various exception types that might occur."""
        # Test with an instance that has a DoesNotExist exception different from the typical pattern
        mock_instance = Mock()

        # Create a custom exception class that follows Django's pattern
        class CustomDoesNotExistError(Exception):
            pass

        mock_instance.DoesNotExist = CustomDoesNotExistError

        # Create a property that raises the custom exception
        def raise_custom_exception():
            raise CustomDoesNotExistError("Custom does not exist")

        type(mock_instance).custom_field = property(lambda self: raise_custom_exception())

        result = get_related_object_safely(mock_instance, "custom_field", default="custom_default")
        self.assertEqual(result, "custom_default")

    def test_get_count_safely_with_different_exception_types(self):
        """Test get_count_safely with various exception types."""
        exception_types = [
            ValueError("Invalid value"),
            TypeError("Wrong type"),
            AttributeError("Missing attribute"),
            RuntimeError("Runtime error"),
        ]

        for exception in exception_types:
            with self.subTest(exception=type(exception).__name__):
                mock_queryset = Mock()
                mock_queryset.count.side_effect = exception

                with patch("apps.core.utils.logger") as mock_logger:
                    result = get_count_safely(mock_queryset)

                self.assertEqual(result, 0)
                mock_logger.warning.assert_called_once()
                # Reset the mock for the next iteration
                mock_logger.reset_mock()
