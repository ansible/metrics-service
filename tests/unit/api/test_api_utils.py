"""
Tests for API utility functions.
"""

import logging
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from apps.api.utils import (
    build_error_response,
    get_count_safely,
)


@pytest.mark.unit
class ApiUtilsTestCase(TestCase):
    """Test cases for API utility functions."""

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

        with patch("apps.api.utils.logger") as mock_logger:
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

    @patch("apps.api.utils.timezone")
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

    @patch("apps.api.utils.timezone")
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

    @patch("apps.api.utils.timezone")
    def test_build_error_response_custom_status_code(self, mock_timezone):
        """Test error response with custom status code."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        result = build_error_response("Server error", status_code=500)

        self.assertEqual(result["status_code"], 500)
        self.assertEqual(result["error"], "Server error")
        self.assertEqual(result["timestamp"], "2023-01-01T12:00:00")

    @patch("apps.api.utils.timezone")
    def test_build_error_response_empty_details(self, mock_timezone):
        """Test error response with empty details dictionary."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2023-01-01T12:00:00"
        mock_timezone.now.return_value = mock_now

        result = build_error_response("Test error", details={})

        # Empty details dictionary is falsy, so it should not be included
        self.assertNotIn("details", result)

    @patch("apps.api.utils.timezone")
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

    @patch("apps.api.utils.timezone")
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

    @patch("apps.api.utils.timezone")
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

    @patch("apps.api.utils.timezone")
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

    @patch("apps.api.utils.timezone")
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
        from apps.api.utils import logger

        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "apps.api.utils")

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

                with patch("apps.api.utils.logger") as mock_logger:
                    result = get_count_safely(mock_queryset)

                self.assertEqual(result, 0)
                mock_logger.warning.assert_called_once()
                # Reset the mock for the next iteration
                mock_logger.reset_mock()
