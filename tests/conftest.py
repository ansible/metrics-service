"""
Pytest configuration and fixtures for metrics_service tests.
"""

import os
import django
from django.conf import settings

# Configure Django settings before any imports
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings.test")
    django.setup()

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient

from apps.core.models import Organization, Team, Animal

User = get_user_model()


@pytest.fixture(scope="session", autouse=True)
def setup_service_id(django_db_setup, django_db_blocker):
    """Mock ServiceID access for tests to prevent ansible_base resource registry errors."""
    import uuid
    from unittest.mock import patch

    # Generate a fixed UUID for consistent testing
    test_service_id = str(uuid.UUID("12345678-1234-5678-9012-123456789012"))

    # Mock the service_id function to return our test UUID
    def mock_service_id():
        return test_service_id

    # Apply patches for the entire test session
    patches = []
    try:
        # Patch the service_id function
        service_id_patch = patch(
            "ansible_base.resource_registry.models.service_identifier.service_id", side_effect=mock_service_id
        )
        patches.append(service_id_patch)

        # Also patch the global variable
        global_var_patch = patch(
            "ansible_base.resource_registry.models.service_identifier._service_id", test_service_id
        )
        patches.append(global_var_patch)

        # Start all patches
        for p in patches:
            p.start()

    except ImportError:
        # If ansible_base is not available, continue anyway
        pass


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def api_client():
    """DRF API test client."""
    return APIClient()


@pytest.fixture
def user():
    """Create a test user."""
    return User.objects.create_superuser(username="testuser", email="test@example.com", password="testpassword123")


@pytest.fixture
def admin_user():
    """Create a test admin user."""
    return User.objects.create_user(
        username="admin", email="admin@example.com", password="adminpassword123", is_staff=True, is_superuser=True
    )


@pytest.fixture
def organization():
    """Create a test organization."""
    return Organization.objects.create(name="Test Organization")


@pytest.fixture
def team(organization):
    """Create a test team."""
    return Team.objects.create(name="Test Team", organization=organization)


@pytest.fixture
def animal(user):
    """Create a test animal."""
    return Animal.objects.create(name="Test Pet", kind="dog", age=3, owner=user)


@pytest.fixture
def authenticated_client(api_client, user):
    """API client authenticated with a test user."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """API client authenticated with an admin user."""
    api_client.force_authenticate(user=admin_user)
    return api_client
