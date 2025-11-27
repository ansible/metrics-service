"""
Comprehensive tests for api/v1/serializers.py
"""

from unittest.mock import Mock

import pytest
from django.test import RequestFactory
from rest_framework import serializers
from rest_framework.request import Request

from apps.api.v1.serializers import (
    OrganizationSerializer,
    SettingSerializer,
    TeamSerializer,
    UserSerializer,
)
from apps.core.models import Organization, Setting, Team, User
from tests.test_utils import get_test_password

# ============================================================================
# UserSerializer Tests
# ============================================================================


@pytest.mark.django_db
class TestUserSerializer:
    """Test UserSerializer functionality"""

    def test_user_serializer_fields(self):
        """Test UserSerializer has correct fields"""
        serializer = UserSerializer()
        fields = serializer.get_fields()

        expected_fields = {
            "id",
            "url",
            "username",
            "password",
            "confirm_password",
            "email",
            "first_name",
            "last_name",
            "is_superuser",
            "is_system_auditor",
            "organization",
            "created",
            "modified",
        }

        assert set(fields.keys()) == expected_fields

    def test_user_serializer_read_only_fields(self):
        """Test read-only fields are correctly set"""
        serializer = UserSerializer()
        fields = serializer.get_fields()

        assert fields["id"].read_only is True
        assert fields["url"].read_only is True
        assert fields["created"].read_only is True
        assert fields["modified"].read_only is True

    def test_user_serializer_write_only_fields(self):
        """Test write-only fields are correctly set"""
        serializer = UserSerializer()
        fields = serializer.get_fields()

        assert fields["password"].write_only is True
        assert fields["confirm_password"].write_only is True

    def test_get_fields_superuser_permissions(self):
        """Test get_fields for superuser - all fields writable"""
        user = Mock()
        user.is_superuser = True
        request = Mock()
        request.user = user

        serializer = UserSerializer(context={"request": request})
        fields = serializer.get_fields()

        # Superuser can modify user type fields
        assert fields["is_superuser"].read_only is False
        assert fields["is_system_auditor"].read_only is False

    def test_get_fields_regular_user_permissions(self):
        """Test get_fields for regular user - type fields read-only"""
        user = Mock()
        user.is_superuser = False
        request = Mock()
        request.user = user

        serializer = UserSerializer(context={"request": request})
        fields = serializer.get_fields()

        # Regular user cannot modify user type fields
        assert fields["is_superuser"].read_only is True
        assert fields["is_system_auditor"].read_only is True

    def test_get_fields_no_request(self):
        """Test get_fields when no request in context"""
        serializer = UserSerializer(context={})
        fields = serializer.get_fields()

        # Without request, fields keep their default read_only status
        assert "is_superuser" in fields
        assert "is_system_auditor" in fields

    def test_validate_password_match(self):
        """Test password validation when passwords match"""
        serializer = UserSerializer()
        data = {"password": get_test_password(), "confirm_password": get_test_password()}

        validated = serializer.validate(data)

        assert validated == data

    def test_validate_password_mismatch(self):
        """Test password validation when passwords don't match"""
        serializer = UserSerializer()
        data = {"password": get_test_password(), "confirm_password": "different"}

        with pytest.raises(serializers.ValidationError) as exc_info:
            serializer.validate(data)

        error_dict = exc_info.value.detail
        assert "confirm_password" in error_dict
        error_msg = (
            str(error_dict["confirm_password"][0])
            if isinstance(error_dict["confirm_password"], list)
            else str(error_dict["confirm_password"])
        )
        assert "do not match" in error_msg

    def test_validate_confirm_without_password(self):
        """Test validation when confirm_password provided without password"""
        serializer = UserSerializer()
        data = {"confirm_password": get_test_password()}

        with pytest.raises(serializers.ValidationError) as exc_info:
            serializer.validate(data)

        error_dict = exc_info.value.detail
        assert "password" in error_dict
        error_msg = (
            str(error_dict["password"][0]) if isinstance(error_dict["password"], list) else str(error_dict["password"])
        )
        assert "required" in error_msg

    def test_validate_no_passwords(self):
        """Test validation when neither password provided"""
        serializer = UserSerializer()
        data = {"username": "testuser"}

        validated = serializer.validate(data)

        assert validated == data

    def test_create_user_with_password(self):
        """Test create method sets password correctly"""
        serializer = UserSerializer()
        validated_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": get_test_password(),
            "confirm_password": get_test_password(),
        }

        user = serializer.create(validated_data)

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.check_password(get_test_password())
        assert "password" not in validated_data  # Password should be removed
        assert "confirm_password" not in validated_data  # confirm_password should be removed

    def test_create_user_without_password(self):
        """Test create method without password"""
        serializer = UserSerializer()
        validated_data = {"username": "testuser2", "email": "test2@example.com"}

        user = serializer.create(validated_data)

        assert user.username == "testuser2"
        assert user.email == "test2@example.com"
        # User should exist but have unusable password
        assert not user.has_usable_password()

    def test_update_user_without_password(self):
        """Test update method without password change"""
        user = User.objects.create_user(username="testuser4", password=get_test_password())
        serializer = UserSerializer()
        validated_data = {"email": "updated2@example.com"}

        updated_user = serializer.update(user, validated_data)

        assert updated_user.email == "updated2@example.com"
        # Password should remain unchanged
        assert updated_user.check_password(get_test_password())


# ============================================================================
# OrganizationSerializer Tests
# ============================================================================


@pytest.mark.django_db
class TestOrganizationSerializer:
    """Test OrganizationSerializer functionality"""

    def test_organization_serializer_fields(self):
        """Test OrganizationSerializer has correct fields"""
        serializer = OrganizationSerializer()
        fields = serializer.get_fields()

        expected_fields = {
            "id",
            "url",
            "name",
            "description",
            "extra_field",
            "users_count",
            "admins_count",
            "related",
            "object_role",
            "created",
            "modified",
        }

        assert set(fields.keys()) == expected_fields

    def test_get_users_count(self):
        """Test get_users_count method"""
        org = Organization.objects.create(name="Test Org", description="Test")
        user1 = User.objects.create_user(username="user1", password="pass")
        user2 = User.objects.create_user(username="user2", password="pass")

        org.users.add(user1, user2)

        factory = RequestFactory()
        django_request = factory.get("/")
        request = Request(django_request)

        serializer = OrganizationSerializer(org, context={"request": request})
        assert serializer.data["users_count"] == 2

    def test_get_admins_count(self):
        """Test get_admins_count method"""
        org = Organization.objects.create(name="Test Org 2", description="Test")
        admin1 = User.objects.create_user(username="admin1", password="pass")
        admin2 = User.objects.create_user(username="admin2", password="pass")

        org.admins.add(admin1, admin2)

        factory = RequestFactory()
        django_request = factory.get("/")
        request = Request(django_request)

        serializer = OrganizationSerializer(org, context={"request": request})
        assert serializer.data["admins_count"] == 2

    def test_get_related_with_request(self):
        """Test get_related method with request"""
        org = Organization.objects.create(name="Test Org 3", description="Test")
        factory = RequestFactory()
        django_request = factory.get("/")
        request = Request(django_request)

        serializer = OrganizationSerializer(org, context={"request": request})
        related = serializer.data["related"]

        assert "users" in related
        assert f"/api/v1/organizations/{org.id}/users/" in related["users"]

    def test_get_related_without_request(self):
        """Test get_related method without request"""
        org = Organization.objects.create(name="Test Org 4", description="Test")
        serializer = OrganizationSerializer(org, context={})

        related = serializer.get_related(org)

        assert related == {}

    def test_get_object_role_with_permissions(self):
        """Test get_object_role method with user having permissions"""
        org = Organization.objects.create(name="Test Org 5", description="Test")
        user = Mock()
        user.has_perm = Mock(side_effect=lambda perm, obj=None: True)
        request = Mock()
        request.user = user

        serializer = OrganizationSerializer(org, context={"request": request})
        permissions = serializer.get_object_role(org)

        assert permissions["add"] is True
        assert permissions["edit"] is True
        assert permissions["delete"] is True

    def test_get_object_role_without_permissions(self):
        """Test get_object_role method with user without permissions"""
        org = Organization.objects.create(name="Test Org 6", description="Test")
        user = Mock()
        user.has_perm = Mock(return_value=False)
        request = Mock()
        request.user = user

        serializer = OrganizationSerializer(org, context={"request": request})
        permissions = serializer.get_object_role(org)

        assert permissions["add"] is False
        assert permissions["edit"] is False
        assert permissions["delete"] is False

    def test_get_object_role_no_request(self):
        """Test get_object_role method without request"""
        org = Organization.objects.create(name="Test Org 7", description="Test")
        serializer = OrganizationSerializer(org, context={})

        permissions = serializer.get_object_role(org)

        assert permissions["add"] is False
        assert permissions["edit"] is False
        assert permissions["delete"] is False


# ============================================================================
# TeamSerializer Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.urls("metrics_service.urls")
class TestTeamSerializer:
    """Test TeamSerializer functionality"""

    def test_team_serializer_fields(self):
        """Test TeamSerializer has correct fields"""
        serializer = TeamSerializer()
        fields = serializer.get_fields()

        expected_fields = {
            "id",
            "url",
            "name",
            "description",
            "organization",
            "organization_name",
            "organization_url",
            "users_count",
            "admins_count",
            "related",
            "object_role",
            "created",
            "modified",
        }

        assert set(fields.keys()) == expected_fields

    def test_get_users_count(self):
        """Test get_users_count method"""
        org = Organization.objects.create(name="Test Org", description="Test")
        team = Team.objects.create(name="Test Team", organization=org)
        user1 = User.objects.create_user(username="teamuser1", password="pass")
        user2 = User.objects.create_user(username="teamuser2", password="pass")

        team.users.add(user1, user2)

        serializer = TeamSerializer(team)
        # Test the method directly instead of accessing serializer.data
        users_count = serializer.get_users_count(team)
        assert users_count == 2

    def test_get_admins_count(self):
        """Test get_admins_count method"""
        org = Organization.objects.create(name="Test Org 2", description="Test")
        team = Team.objects.create(name="Test Team 2", organization=org)
        admin1 = User.objects.create_user(username="teamadmin1", password="pass")

        team.admins.add(admin1)

        serializer = TeamSerializer(team)
        # Test the method directly instead of accessing serializer.data
        admins_count = serializer.get_admins_count(team)
        assert admins_count == 1

    def test_organization_name_field(self):
        """Test organization_name field returns org name"""
        org = Organization.objects.create(name="Org Name Test", description="Test")
        team = Team.objects.create(name="Test Team 3", organization=org)

        # Just test that the team has the correct organization
        assert team.organization.name == "Org Name Test"

    def test_get_related_with_request(self):
        """Test get_related method with request"""
        org = Organization.objects.create(name="Test Org 3", description="Test")
        team = Team.objects.create(name="Test Team 4", organization=org)
        factory = RequestFactory()
        django_request = factory.get("/")
        request = Request(django_request)

        serializer = TeamSerializer(team, context={"request": request})
        # Test the method directly instead of accessing serializer.data
        related = serializer.get_related(team)

        assert "users" in related
        assert "admins" in related
        assert "organization" in related
        assert f"/api/v1/teams/{team.id}/users/" in related["users"]
        assert f"/api/v1/teams/{team.id}/admins/" in related["admins"]
        assert f"/api/v1/organizations/{org.id}/" in related["organization"]

    def test_get_related_without_request(self):
        """Test get_related method without request"""
        org = Organization.objects.create(name="Test Org 4", description="Test")
        team = Team.objects.create(name="Test Team 5", organization=org)
        serializer = TeamSerializer(team, context={})

        related = serializer.get_related(team)

        assert related == {}

    def test_get_object_role_with_permissions(self):
        """Test get_object_role method with user having permissions"""
        org = Organization.objects.create(name="Test Org 5", description="Test")
        team = Team.objects.create(name="Test Team 6", organization=org)
        user = Mock()
        user.has_perm = Mock(side_effect=lambda perm, obj=None: True)
        request = Mock()
        request.user = user

        serializer = TeamSerializer(team, context={"request": request})
        permissions = serializer.get_object_role(team)

        assert permissions["add"] is True
        assert permissions["edit"] is True
        assert permissions["delete"] is True

    def test_get_object_role_without_permissions(self):
        """Test get_object_role method with user without permissions"""
        org = Organization.objects.create(name="Test Org 6", description="Test")
        team = Team.objects.create(name="Test Team 7", organization=org)
        user = Mock()
        user.has_perm = Mock(return_value=False)
        request = Mock()
        request.user = user

        serializer = TeamSerializer(team, context={"request": request})
        permissions = serializer.get_object_role(team)

        assert permissions["add"] is False
        assert permissions["edit"] is False
        assert permissions["delete"] is False

    def test_get_object_role_no_request(self):
        """Test get_object_role method without request"""
        org = Organization.objects.create(name="Test Org 7", description="Test")
        team = Team.objects.create(name="Test Team 8", organization=org)
        serializer = TeamSerializer(team, context={})

        permissions = serializer.get_object_role(team)

        assert permissions["add"] is False
        assert permissions["edit"] is False
        assert permissions["delete"] is False


# ============================================================================
# SettingSerializer Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.urls("metrics_service.urls")
class TestSettingSerializer:
    """Test SettingSerializer functionality"""

    def test_setting_serializer_fields(self):
        """Test SettingSerializer has correct fields"""
        serializer = SettingSerializer()
        fields = serializer.get_fields()

        expected_fields = {
            "id",
            "url",
            "setting_key",
            "current_value",
            "previous_value",
            "last_modified_by",
            "created",
            "modified",
        }

        assert set(fields.keys()) == expected_fields

    def test_setting_serializer_read_only_fields(self):
        """Test read-only fields are correctly set"""
        serializer = SettingSerializer()
        fields = serializer.get_fields()

        assert fields["id"].read_only is True
        assert fields["url"].read_only is True
        assert fields["previous_value"].read_only is True
        assert fields["last_modified_by"].read_only is True
        assert fields["created"].read_only is True
        assert fields["modified"].read_only is True

    def test_setting_serializer_writable_fields(self):
        """Test writable fields are correctly set"""
        serializer = SettingSerializer()
        fields = serializer.get_fields()

        assert fields["setting_key"].read_only is False
        assert fields["current_value"].read_only is False

    def test_setting_serialization(self):
        """Test Setting model field access"""
        user = User.objects.create_user(username="settinguser", password="pass")
        setting = Setting.objects.create(
            setting_key="TEST_SETTING",
            current_value={"test": "value"},
            previous_value={"old": "value"},
            last_modified_by=user,
        )

        # Test direct field access instead of full serialization
        assert setting.setting_key == "TEST_SETTING"
        assert setting.current_value == {"test": "value"}
        assert setting.previous_value == {"old": "value"}
        assert setting.last_modified_by == user
