"""
Unit tests for OutputFormatter service.
"""

from io import StringIO
from unittest.mock import MagicMock

import pytest
from django.test import TestCase

from apps.tasks.services.output_formatter import OutputFormatter


@pytest.mark.unit
class OutputFormatterTestCase(TestCase):
    """Test cases for OutputFormatter service."""

    def setUp(self):
        """Set up test fixtures."""
        self.stdout = StringIO()
        self.style = MagicMock()
        self.style.SUCCESS.return_value = "SUCCESS: message"
        self.style.ERROR.return_value = "ERROR: message"
        self.style.WARNING.return_value = "WARNING: message"
        self.formatter = OutputFormatter(self.stdout, self.style)

    def test_initialization(self):
        """Test OutputFormatter initialization."""
        self.assertEqual(self.formatter.stdout, self.stdout)
        self.assertEqual(self.formatter.style, self.style)

    def test_success_message(self):
        """Test success message formatting."""
        self.formatter.success("Test success")

        self.style.SUCCESS.assert_called_once_with("Test success")
        output = self.stdout.getvalue()
        self.assertIn("SUCCESS: message", output)

    def test_error_message(self):
        """Test error message formatting."""
        self.formatter.error("Test error")

        self.style.ERROR.assert_called_once_with("Test error")
        output = self.stdout.getvalue()
        self.assertIn("ERROR: message", output)

    def test_warning_message(self):
        """Test warning message formatting."""
        self.formatter.warning("Test warning")

        self.style.WARNING.assert_called_once_with("Test warning")
        output = self.stdout.getvalue()
        self.assertIn("WARNING: message", output)

    def test_info_message(self):
        """Test info message formatting."""
        self.formatter.info("Test info")

        # Info doesn't use style formatting
        self.style.SUCCESS.assert_not_called()
        self.style.ERROR.assert_not_called()
        self.style.WARNING.assert_not_called()

        output = self.stdout.getvalue()
        self.assertEqual(output.strip(), "Test info")

    def test_write_message(self):
        """Test plain write message."""
        self.formatter.write("Plain message")

        output = self.stdout.getvalue()
        self.assertEqual(output.strip(), "Plain message")

    def test_write_separator_default(self):
        """Test write separator with default parameters."""
        self.formatter.write_separator()

        output = self.stdout.getvalue()
        self.assertEqual(output.strip(), "=" * 50)

    def test_write_separator_custom(self):
        """Test write separator with custom parameters."""
        self.formatter.write_separator("-", 20)

        output = self.stdout.getvalue()
        self.assertEqual(output.strip(), "-" * 20)

    def test_write_header_default(self):
        """Test write header with default parameters."""
        self.formatter.write_header("Test Header")

        output = self.stdout.getvalue()
        lines = output.strip().split("\n")
        self.assertEqual(lines[0], "Test Header==================================================")

    def test_write_header_custom(self):
        """Test write header with custom parameters."""
        self.formatter.write_header("Custom Header", "*", 30)

        output = self.stdout.getvalue()
        lines = output.strip().split("\n")
        self.assertEqual(lines[0], "Custom Header******************************")

    def test_multiple_messages(self):
        """Test multiple message formatting."""
        self.formatter.success("Success 1")
        self.formatter.error("Error 1")
        self.formatter.warning("Warning 1")
        self.formatter.info("Info 1")
        self.formatter.write("Plain 1")

        # Verify all style methods were called
        self.style.SUCCESS.assert_called_with("Success 1")
        self.style.ERROR.assert_called_with("Error 1")
        self.style.WARNING.assert_called_with("Warning 1")

        # Verify output contains all messages
        output = self.stdout.getvalue()
        self.assertIn("SUCCESS: message", output)
        self.assertIn("ERROR: message", output)
        self.assertIn("WARNING: message", output)
        self.assertIn("Info 1", output)
        self.assertIn("Plain 1", output)

    def test_empty_messages(self):
        """Test empty message handling."""
        self.formatter.success("")
        self.formatter.error("")
        self.formatter.warning("")
        self.formatter.info("")
        self.formatter.write("")

        # Verify style methods were called with empty strings
        self.style.SUCCESS.assert_called_with("")
        self.style.ERROR.assert_called_with("")
        self.style.WARNING.assert_called_with("")

        # Should not raise any exceptions
        output = self.stdout.getvalue()
        self.assertIsInstance(output, str)

    def test_unicode_messages(self):
        """Test unicode message handling."""
        unicode_msg = "Test with unicode: 🎉 ✅ ⚠️ ❌"

        self.formatter.success(unicode_msg)
        self.formatter.error(unicode_msg)
        self.formatter.warning(unicode_msg)
        self.formatter.info(unicode_msg)
        self.formatter.write(unicode_msg)

        # Verify style methods were called with unicode
        self.style.SUCCESS.assert_called_with(unicode_msg)
        self.style.ERROR.assert_called_with(unicode_msg)
        self.style.WARNING.assert_called_with(unicode_msg)

        # Verify unicode is handled properly
        output = self.stdout.getvalue()
        self.assertIn("🎉", output)
        self.assertIn("✅", output)
        self.assertIn("⚠️", output)
        self.assertIn("❌", output)
