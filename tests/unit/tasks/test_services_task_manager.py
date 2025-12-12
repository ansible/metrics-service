"""
Unit tests for TaskManager service.
"""

import json
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.test import TestCase

from apps.tasks.models import Task
from apps.tasks.services.output_formatter import OutputFormatter
from apps.tasks.services.task_manager import TaskManager

User = get_user_model()


@pytest.mark.unit
class TaskManagerTestCase(TestCase):
    """Test cases for TaskManager service."""

    def setUp(self):
        """Set up test fixtures."""
        self.stdout = StringIO()
        self.style = MagicMock()
        self.output_formatter = OutputFormatter(self.stdout, self.style)
        self.task_manager = TaskManager(self.output_formatter)

        # Create test user
        self.user = User.objects.create_user(username="testuser", email="test@example.com")

    def test_initialization(self):
        """Test TaskManager initialization."""
        self.assertEqual(self.task_manager.output, self.output_formatter)

    def test_create_task_with_exception(self):
        """Test task creation with exception handling."""
        options = {"name": "Failing Task", "function": "test_function", "priority": 2}

        with patch.object(Task.objects, "create", side_effect=Exception("Database error")):
            with self.assertRaises(CommandError) as cm:
                self.task_manager.create_task(options)

            self.assertIn("Failed to create task", str(cm.exception))
            self.assertIn("Database error", str(cm.exception))

    def test_parse_task_data_valid_json(self):
        """Test parsing valid JSON task data."""
        valid_json = '{"key": "value", "number": 123, "list": [1, 2, 3]}'
        result = self.task_manager._parse_task_data(valid_json)

        expected = {"key": "value", "number": 123, "list": [1, 2, 3]}
        self.assertEqual(result, expected)

    def test_parse_task_data_empty(self):
        """Test parsing empty task data."""
        result = self.task_manager._parse_task_data(None)
        self.assertEqual(result, {})

        result = self.task_manager._parse_task_data("")
        self.assertEqual(result, {})

    def test_parse_task_data_invalid_json(self):
        """Test parsing invalid JSON task data."""
        invalid_json = '{"key": value, "incomplete":'

        with self.assertRaises(CommandError) as cm:
            self.task_manager._parse_task_data(invalid_json)

        self.assertIn("Invalid JSON in --data argument", str(cm.exception))

    def test_parse_scheduled_time_valid(self):
        """Test parsing valid scheduled time."""
        time_str = "2024-12-31 23:59:59"
        result = self.task_manager._parse_scheduled_time(time_str)

        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 31)
        self.assertEqual(result.hour, 23)
        self.assertEqual(result.minute, 59)
        self.assertEqual(result.second, 59)
        # Should be timezone-aware
        self.assertIsNotNone(result.tzinfo)

    def test_parse_scheduled_time_empty(self):
        """Test parsing empty scheduled time."""
        result = self.task_manager._parse_scheduled_time(None)
        self.assertIsNone(result)

        result = self.task_manager._parse_scheduled_time("")
        self.assertIsNone(result)

    def test_parse_scheduled_time_invalid_format(self):
        """Test parsing invalid scheduled time format."""
        invalid_formats = [
            "2024-12-31",  # Missing time
            "23:59:59",  # Missing date
            "2024/12/31 23:59:59",  # Wrong date format
            "invalid",  # Completely invalid
            "2024-13-31 23:59:59",  # Invalid month
        ]

        for invalid_format in invalid_formats:
            with self.assertRaises(CommandError) as cm:
                self.task_manager._parse_scheduled_time(invalid_format)

            self.assertIn("Invalid scheduled_time format", str(cm.exception))

    def test_get_user_valid(self):
        """Test getting valid user."""
        result = self.task_manager._get_user("testuser")
        self.assertEqual(result, self.user)

    def test_get_user_empty(self):
        """Test getting user with empty username."""
        result = self.task_manager._get_user(None)
        self.assertIsNone(result)

        result = self.task_manager._get_user("")
        self.assertIsNone(result)

    def test_get_user_not_found(self):
        """Test getting non-existent user."""
        with self.assertRaises(CommandError) as cm:
            self.task_manager._get_user("nonexistent")

        self.assertIn("User 'nonexistent' not found", str(cm.exception))

    def test_edge_case_complex_json_data(self):
        """Test parsing complex JSON data structures."""
        complex_json = json.dumps(
            {
                "nested": {"dict": {"key": "value"}, "list": [1, 2, {"inner": "value"}]},
                "unicode": "测试 🎉",
                "numbers": [1.5, -42, 0],
                "booleans": [True, False, None],
            }
        )

        result = self.task_manager._parse_task_data(complex_json)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["nested"]["dict"]["key"], "value")
        self.assertEqual(result["unicode"], "测试 🎉")
        self.assertEqual(result["numbers"], [1.5, -42, 0])
        self.assertEqual(result["booleans"], [True, False, None])
