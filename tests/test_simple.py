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

    def test_hello_world(self):
        """Test hello_world task function."""
        from apps.tasks.tasks import hello_world

        result = hello_world()

        self.assertEqual(result["status"], "success")


class TestTaskScheduler(BaseTaskSchedulerTest):
    """Test TaskScheduler class."""


class TestUtilities(BaseUtilitiesTest):
    """Test utility functions."""
