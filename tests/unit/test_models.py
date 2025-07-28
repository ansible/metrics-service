"""
Unit tests for core models.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.core.models import Animal, Organization, Team

User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
class TestUserModel:
    """Test cases for User model."""

    def test_user_creation(self):
        """Test user can be created successfully."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpassword123")
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.check_password("testpassword123")

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
        assert str(team) == f"{organization.name} - Test Team"


@pytest.mark.unit
@pytest.mark.django_db
class TestAnimalModel:
    """Test cases for Animal model."""

    def test_animal_creation(self, user):
        """Test animal can be created successfully."""
        animal = Animal.objects.create(name="Buddy", kind="dog", age=3, owner=user)
        assert animal.name == "Buddy"
        assert animal.kind == "dog"
        assert animal.age == 3
        assert animal.owner == user

    def test_animal_string_representation(self, user):
        """Test animal string representation."""
        animal = Animal.objects.create(name="Buddy", kind="dog", owner=user)
        assert str(animal) == "Buddy (Dog)"

    def test_animal_kind_choices(self, user):
        """Test animal kind validation."""
        # Valid choice
        animal = Animal.objects.create(name="Buddy", kind="cat", owner=user)
        assert animal.kind == "cat"

        # The model doesn't enforce validation at creation,
        # but we can test the choices are defined
        choices = dict(Animal.ANIMAL_KINDS)
        assert "dog" in choices
        assert "cat" in choices
        assert "bird" in choices
        assert "fish" in choices
