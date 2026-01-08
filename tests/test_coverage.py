"""
Simplified tests for coverage without complex Django setup.
"""

import pytest

from .test_common import (
    BaseTaskFunctionsTest,
    BaseTaskSchedulerTest,
    BaseUtilitiesTest,
)


class TestTaskFunctions(BaseTaskFunctionsTest):
    """Test task functions directly without model dependencies."""

    @pytest.mark.django_db
    def test_cleanup_old_data(self):
        """Test cleanup_old_data function."""
        from apps.tasks.tasks import cleanup_old_data

        result = cleanup_old_data(days_old=30)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["days_old"], 30)


class TestTaskScheduler(BaseTaskSchedulerTest):
    """Test TaskScheduler class."""


class TestUtilities(BaseUtilitiesTest):
    """Test utility functions."""

    def test_placeholder(self):
        """Placeholder test for utilities."""
        # Password validation functions were removed with simplified User model
