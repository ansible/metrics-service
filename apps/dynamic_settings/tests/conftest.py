"""
Pytest fixtures for dynamic_settings tests.
"""

import pytest
from django.contrib.auth import get_user_model

from tests.test_utils import get_test_password

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(username="testuser", email="test@example.com", password=get_test_password())


@pytest.fixture
def admin_user(db):
    """Create an admin user."""
    return User.objects.create_superuser(username="admin", email="admin@example.com", password="admin123")
