"""
Simplified tests for coverage without complex Django setup.
"""

from unittest.mock import Mock, patch

import pytest

from .test_common import (
    BaseTaskFunctionsTest,
    BaseTaskSchedulerTest,
    BaseUtilitiesTest,
    setup_django_for_tests,
)

# Setup Django for testing
setup_django_for_tests()


class TestTaskFunctions(BaseTaskFunctionsTest):
    """Test task functions directly without model dependencies."""

    @pytest.mark.django_db
    @patch("django.contrib.auth.get_user_model")
    def test_process_user_data(self, mock_get_user_model):
        """Test process_user_data function."""
        from apps.tasks import process_user_data

        # Mock user and user model
        mock_user = Mock()
        mock_user.username = "testuser"
        mock_user.id = 1

        mock_user_model = Mock()
        mock_user_model.objects.get.return_value = mock_user
        mock_get_user_model.return_value = mock_user_model

        result = process_user_data(user_id=1, operation="sync")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["user_id"], 1)
        self.assertEqual(result["username"], "testuser")
        self.assertEqual(result["operation"], "sync")


class TestTaskScheduler(BaseTaskSchedulerTest):
    """Test TaskScheduler class."""


class TestUtilities(BaseUtilitiesTest):
    """Test utility functions."""

    def test_password_validation(self):
        """Test password validation if available."""
        try:
            from apps.core.models import password_is_hashed, password_is_usable

            # Test with mock password
            self.assertFalse(password_is_hashed("plaintext"))
            self.assertTrue(password_is_usable("password"))

        except ImportError:
            # DAB not available, skip test
            pass


if __name__ == "__main__":
    import unittest

    unittest.main()
