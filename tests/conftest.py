"""
Pytest configuration and fixtures for metrics_service tests.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient

from apps.core.models import Organization, Team, Animal

User = get_user_model()


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
    return User.objects.create_user(username="testuser", email="test@example.com", password="testpassword123")


@pytest.fixture
def admin_user():
    """Create a test admin user."""
    return User.objects.create_user(
        username="admin", email="admin@example.com", password="adminpassword123", is_staff=True, is_superuser=True
    )


@pytest.fixture
def organization():
    """Create a test organization."""
    return Organization.objects.create(name="Test Organization", description="A test organization")


@pytest.fixture
def team(organization):
    """Create a test team."""
    return Team.objects.create(name="Test Team", organization=organization, description="A test team")


@pytest.fixture
def animal(user):
    """Create a test animal."""
    return Animal.objects.create(name="Test Pet", kind="dog", age=3, owner=user, description="A test animal")


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
