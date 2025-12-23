"""
Simple tests that actually work without complex Django setup.
"""

from .test_common import (
    BaseTaskFunctionsTest,
    BaseTaskSchedulerTest,
    BaseUtilitiesTest,
)


class TestTaskFunctions(BaseTaskFunctionsTest):
    """Test task functions directly."""

    def test_cleanup_old_data_default_values(self):
        """Test cleanup_old_data with default values."""
        from apps.tasks.tasks import cleanup_old_data

        result = cleanup_old_data()

        self.assertEqual(result["status"], "success")


class TestTaskScheduler(BaseTaskSchedulerTest):
    """Test TaskScheduler class."""


class TestUtilities(BaseUtilitiesTest):
    """Test utility functions."""
