"""
Unit tests for core models.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.core.models import Organization, Team

User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
class TestUserModel:
    """Test cases for User model."""

    def test_user_creation(self):
        """Test user can be created successfully."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpassword123")  # noqa: S105
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.check_password("testpassword123")  # noqa: S105

    def test_user_string_representation(self):
        """Test user string representation."""
        user = User.objects.create_user(username="testuser")
        assert str(user) == "testuser"


@pytest.mark.unit
@pytest.mark.django_db
class TestOrganizationModel:
    """Test cases for Organization model."""

    def test_organization_creation(self):
        """Test organization can be created successfully."""
        org = Organization.objects.create(name="Test Org", description="A test organization")
        assert org.name == "Test Org"
        assert org.description == "A test organization"

    def test_organization_string_representation(self):
        """Test organization string representation."""
        org = Organization.objects.create(name="Test Org")
        assert str(org) == "Test Org"


@pytest.mark.unit
@pytest.mark.django_db
class TestTeamModel:
    """Test cases for Team model."""

    def test_team_creation(self, organization):
        """Test team can be created successfully."""
        team = Team.objects.create(name="Test Team", organization=organization, description="A test team")
        assert team.name == "Test Team"
        assert team.organization == organization
        assert team.description == "A test team"

    def test_team_string_representation(self, organization):
        """Test team string representation."""
        team = Team.objects.create(name="Test Team", organization=organization)
        # AbstractTeam's __str__ returns just the team name
        assert str(team) == "Test Team"
