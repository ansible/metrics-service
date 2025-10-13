"""
Comprehensive tests for apps/api/v1/base_views.py to achieve 100% code coverage.
"""

from unittest.mock import Mock, patch

import pytest
from django.db import models
from django.test import TestCase
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from apps.api.v1.base_views import BaseViewSet, SearchFilterMixin, UserManagementMixin
from apps.core.models import Organization, User


# Mock serializer for testing BaseViewSet
class MockSerializer(serializers.Serializer):
    name = serializers.CharField()

    class Meta:
        model = User
        fields = ["name"]


# Mock model for testing
class MockModel(models.Model):
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        app_label = "test"

    @classmethod
    def access_qs(cls, user, queryset=None):
        """Mock access_qs method"""
        return queryset.filter(name__icontains="test") if queryset else cls.objects.filter(name__icontains="test")


# Mock model without access_qs for testing fallback
class MockModelNoAccess(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "test"


# Test ViewSet using BaseViewSet
class MockViewSetForTesting(BaseViewSet):
    queryset = MockModel.objects.all()
    serializer_class = MockSerializer


@pytest.mark.django_db
class TestBaseViewSetComprehensive(TestCase):
    """Comprehensive tests for BaseViewSet class."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.admin_user = User.objects.create_superuser(username="admin", email="admin@example.com")
        self.viewset = MockViewSetForTesting()

    def test_base_viewset_initialization(self):
        """Test BaseViewSet can be initialized with proper attributes."""
        viewset = BaseViewSet()

        # Test permission classes
        self.assertIsNotNone(viewset.permission_classes)
        self.assertEqual(len(viewset.permission_classes), 2)

        # Test ordering configuration
        self.assertEqual(viewset.ordering_fields, ["id", "created", "modified"])
        self.assertEqual(viewset.ordering, ["id"])

    def test_get_queryset_with_access_qs(self):
        """Test get_queryset method when model has access_qs method."""
        # Mock request and user
        request = self.factory.get("/")
        request.user = self.user
        self.viewset.request = request

        # Mock queryset with model that has access_qs
        mock_queryset = Mock()
        mock_queryset.model = MockModel
        MockModel.access_qs = Mock(return_value=mock_queryset)
        self.viewset.queryset = mock_queryset

        result = self.viewset.get_queryset()

        # Verify access_qs was called with correct parameters
        MockModel.access_qs.assert_called_once_with(self.user, queryset=mock_queryset)
        self.assertEqual(result, mock_queryset)

    def test_get_queryset_without_access_qs(self):
        """Test get_queryset method when model doesn't have access_qs method."""
        # Mock request and user
        request = self.factory.get("/")
        request.user = self.user
        self.viewset.request = request

        # Mock queryset with model that doesn't have access_qs
        mock_queryset = Mock()
        mock_queryset.model = MockModelNoAccess
        self.viewset.queryset = mock_queryset

        result = self.viewset.get_queryset()

        # Should return the original queryset
        self.assertEqual(result, mock_queryset)

    def test_handle_exception(self):
        """Test handle_exception method logs and calls parent."""
        # Create a test exception
        test_exception = ValidationError("Test validation error")

        # Mock the parent's handle_exception method
        with patch.object(BaseViewSet.__bases__[1], "handle_exception") as mock_parent:
            mock_response = Response({"error": "test"}, status=400)
            mock_parent.return_value = mock_response

            result = self.viewset.handle_exception(test_exception)

            # Verify parent method was called
            mock_parent.assert_called_once_with(test_exception)
            self.assertEqual(result, mock_response)

    def test_perform_create_with_created_by_field_authenticated(self):
        """Test perform_create sets created_by for authenticated user."""
        # Mock serializer with model that has created_by field
        mock_serializer = Mock()
        mock_serializer.Meta.model = MockModel
        mock_serializer.save = Mock()

        # Mock authenticated request
        request = self.factory.post("/")
        request.user = self.user
        self.viewset.request = request

        self.viewset.perform_create(mock_serializer)

        # Verify save was called with created_by
        mock_serializer.save.assert_called_once_with(created_by=self.user)

    def test_perform_create_with_created_by_field_anonymous(self):
        """Test perform_create doesn't set created_by for anonymous user."""
        # Mock serializer with model that has created_by field
        mock_serializer = Mock()
        mock_serializer.Meta.model = MockModel
        mock_serializer.save = Mock()

        # Mock anonymous request
        request = self.factory.post("/")
        request.user = Mock()
        request.user.is_authenticated = False
        self.viewset.request = request

        self.viewset.perform_create(mock_serializer)

        # Verify save was called without created_by
        mock_serializer.save.assert_called_once_with()

    def test_perform_create_without_created_by_field(self):
        """Test perform_create works when model doesn't have created_by field."""
        # Mock serializer with model that doesn't have created_by field
        mock_serializer = Mock()
        mock_serializer.Meta.model = MockModelNoAccess
        mock_serializer.save = Mock()

        # Mock authenticated request
        request = self.factory.post("/")
        request.user = self.user
        self.viewset.request = request

        self.viewset.perform_create(mock_serializer)

        # Verify save was called without created_by
        mock_serializer.save.assert_called_once_with()

    def test_perform_update(self):
        """Test perform_update calls serializer.save()."""
        mock_serializer = Mock()
        mock_serializer.save = Mock()

        self.viewset.perform_update(mock_serializer)

        mock_serializer.save.assert_called_once_with()


@pytest.mark.django_db
class TestUserManagementMixinComprehensive(TestCase):
    """Comprehensive tests for UserManagementMixin class."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user1 = User.objects.create_user(username="user1", email="user1@example.com")
        self.user2 = User.objects.create_user(username="user2", email="user2@example.com")
        self.organization = Organization.objects.create(name="Test Org")

        # Create a test viewset that uses the mixin
        class TestUserManagementViewSet(UserManagementMixin):
            def get_object(self):
                return self.organization

        self.viewset = TestUserManagementViewSet()
        self.viewset.organization = self.organization

    def test_add_user_to_field_missing_user_id(self):
        """Test _add_user_to_field method with missing user_id."""
        # Create DRF request without user_id
        request = Mock()
        request.data = {}

        self.viewset.get_object = Mock(return_value=self.organization)

        response = self.viewset._add_user_to_field(request, "users")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Check if response data has 'detail' key or different structure
        if "detail" in response.data:
            self.assertIn("user_id is required", response.data["detail"])
        else:
            # Check for other possible structures
            response_str = str(response.data)
            self.assertIn("user_id is required", response_str)

    def test_add_user_to_field_user_not_found(self):
        """Test _add_user_to_field method with non-existent user_id."""
        # Create DRF request with non-existent user_id
        request = Mock()
        request.data = {"user_id": 99999}

        self.viewset.get_object = Mock(return_value=self.organization)

        response = self.viewset._add_user_to_field(request, "users")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Check if response data has 'detail' key or different structure
        if "detail" in response.data:
            self.assertIn("User not found", response.data["detail"])
        else:
            # Check for other possible structures
            response_str = str(response.data)
            self.assertIn("User not found", response_str)

    def test_remove_user_from_field_missing_user_id(self):
        """Test _remove_user_from_field method with missing user_id."""
        # Create DRF request without user_id
        request = Mock()
        request.data = {}

        self.viewset.get_object = Mock(return_value=self.organization)

        response = self.viewset._remove_user_from_field(request, "users")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Check if response data has 'detail' key or different structure
        if "detail" in response.data:
            self.assertIn("user_id is required", response.data["detail"])
        else:
            # Check for other possible structures
            response_str = str(response.data)
            self.assertIn("user_id is required", response_str)

    def test_remove_user_from_field_user_not_found(self):
        """Test _remove_user_from_field method with non-existent user_id."""
        # Create DRF request with non-existent user_id
        request = Mock()
        request.data = {"user_id": 99999}

        self.viewset.get_object = Mock(return_value=self.organization)

        response = self.viewset._remove_user_from_field(request, "users")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Check if response data has 'detail' key or different structure
        if "detail" in response.data:
            self.assertIn("User not found", response.data["detail"])
        else:
            # Check for other possible structures
            response_str = str(response.data)
            self.assertIn("User not found", response_str)

    def test_add_user_action(self):
        """Test add_user action method."""
        request = self.factory.post("/", {"user_id": self.user1.id})

        # Mock _add_user_to_field method
        expected_response = Response({"message": "User added successfully"})
        self.viewset._add_user_to_field = Mock(return_value=expected_response)

        response = self.viewset.add_user(request, pk=1)

        self.viewset._add_user_to_field.assert_called_once_with(request, "users", "User added successfully")
        self.assertEqual(response, expected_response)

    def test_remove_user_action(self):
        """Test remove_user action method."""
        request = self.factory.post("/", {"user_id": self.user1.id})

        # Mock _remove_user_from_field method
        expected_response = Response({"message": "User removed successfully"})
        self.viewset._remove_user_from_field = Mock(return_value=expected_response)

        response = self.viewset.remove_user(request, pk=1)

        self.viewset._remove_user_from_field.assert_called_once_with(request, "users", "User removed successfully")
        self.assertEqual(response, expected_response)

    def test_add_admin_action(self):
        """Test add_admin action method."""
        request = self.factory.post("/", {"user_id": self.user1.id})

        # Mock _add_user_to_field method
        expected_response = Response({"message": "Admin added successfully"})
        self.viewset._add_user_to_field = Mock(return_value=expected_response)

        response = self.viewset.add_admin(request, pk=1)

        self.viewset._add_user_to_field.assert_called_once_with(request, "admins", "Admin added successfully")
        self.assertEqual(response, expected_response)

    def test_remove_admin_action(self):
        """Test remove_admin action method."""
        request = self.factory.post("/", {"user_id": self.user1.id})

        # Mock _remove_user_from_field method
        expected_response = Response({"message": "Admin removed successfully"})
        self.viewset._remove_user_from_field = Mock(return_value=expected_response)

        response = self.viewset.remove_admin(request, pk=1)

        self.viewset._remove_user_from_field.assert_called_once_with(request, "admins", "Admin removed successfully")
        self.assertEqual(response, expected_response)


# Mock model for SearchFilterMixin tests
class MockModelForSearch(models.Model):
    name = models.CharField(max_length=100)
    username = models.CharField(max_length=100)
    email = models.EmailField()
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="owned_items")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        app_label = "test"


# Mock model with minimal fields for SearchFilterMixin tests
class MockModelMinimal(models.Model):
    title = models.CharField(max_length=100)  # Different field name to test filtering

    class Meta:
        app_label = "test"


@pytest.mark.django_db
class TestSearchFilterMixinComprehensive(TestCase):
    """Comprehensive tests for SearchFilterMixin class."""

    def setUp(self):
        self.factory = APIRequestFactory()

        # Create a test viewset that uses the mixin
        class TestSearchFilterViewSet(SearchFilterMixin):
            queryset = MockModelForSearch.objects.all()

        self.viewset = TestSearchFilterViewSet()

    def test_get_search_fields_with_all_common_fields(self):
        """Test get_search_fields method with model that has all common text fields."""
        search_fields = self.viewset.get_search_fields()

        expected_fields = [
            "name",
            "username",
            "email",
            "first_name",
            "last_name",
            "description",
            "owner__username",
            "organization__name",
        ]

        for field in expected_fields:
            self.assertIn(field, search_fields)

    def test_get_search_fields_with_minimal_model(self):
        """Test get_search_fields method with model that has minimal fields."""

        # Create viewset with minimal model
        class TestSearchFilterViewSetMinimal(SearchFilterMixin):
            queryset = MockModelMinimal.objects.all()

        viewset = TestSearchFilterViewSetMinimal()
        search_fields = viewset.get_search_fields()

        # Should return empty list since no common fields are present
        self.assertEqual(search_fields, [])

    def test_get_search_fields_without_owner_and_organization(self):
        """Test get_search_fields method with model without owner and organization fields."""

        # Create a model without owner and organization
        class MockModelNoRelated(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()

            class Meta:
                app_label = "test"

        class TestSearchFilterViewSetNoRelated(SearchFilterMixin):
            queryset = MockModelNoRelated.objects.all()

        viewset = TestSearchFilterViewSetNoRelated()
        search_fields = viewset.get_search_fields()

        # Should include name and email but not related fields
        self.assertIn("name", search_fields)
        self.assertIn("email", search_fields)
        self.assertNotIn("owner__username", search_fields)
        self.assertNotIn("organization__name", search_fields)

    def test_get_filterset_fields_with_all_common_fields(self):
        """Test get_filterset_fields method with model that has all common filter fields."""
        filterset_fields = self.viewset.get_filterset_fields()

        # Test text fields
        text_fields = ["name", "username", "email", "description"]
        for field in text_fields:
            self.assertIn(field, filterset_fields)
            self.assertEqual(filterset_fields[field], ["exact", "icontains"])

        # Test boolean fields
        boolean_fields = ["is_active", "is_staff", "is_superuser"]
        for field in boolean_fields:
            self.assertIn(field, filterset_fields)
            self.assertEqual(filterset_fields[field], ["exact"])

        # Test date fields
        date_fields = ["created", "modified", "date_joined"]
        for field in date_fields:
            self.assertIn(field, filterset_fields)
            self.assertEqual(filterset_fields[field], ["gte", "lte"])

    def test_get_filterset_fields_with_minimal_model(self):
        """Test get_filterset_fields method with model that has minimal fields."""

        # Create viewset with minimal model
        class TestSearchFilterViewSetMinimal(SearchFilterMixin):
            queryset = MockModelMinimal.objects.all()

        viewset = TestSearchFilterViewSetMinimal()
        filterset_fields = viewset.get_filterset_fields()

        # Should return empty dict since no common filter fields are present
        self.assertEqual(filterset_fields, {})

    def test_get_filterset_fields_partial_match(self):
        """Test get_filterset_fields method with model that has some common fields."""

        # Create a model with only some common fields
        class MockModelPartial(models.Model):
            name = models.CharField(max_length=100)
            is_active = models.BooleanField(default=True)
            created = models.DateTimeField(auto_now_add=True)
            other_field = models.CharField(max_length=100)  # Should be ignored

            class Meta:
                app_label = "test"

        class TestSearchFilterViewSetPartial(SearchFilterMixin):
            queryset = MockModelPartial.objects.all()

        viewset = TestSearchFilterViewSetPartial()
        filterset_fields = viewset.get_filterset_fields()

        # Should include only the matching fields
        expected_fields = {"name": ["exact", "icontains"], "is_active": ["exact"], "created": ["gte", "lte"]}

        self.assertEqual(filterset_fields, expected_fields)


@pytest.mark.django_db
class TestMixinIntegration(TestCase):
    """Test integration between mixins and base viewset."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.organization = Organization.objects.create(name="Test Org")

        # Create a comprehensive viewset that uses all mixins
        class ComprehensiveViewSet(BaseViewSet, UserManagementMixin, SearchFilterMixin):
            queryset = Organization.objects.all()
            serializer_class = MockSerializer

        self.viewset = ComprehensiveViewSet()

    def test_combined_mixin_functionality(self):
        """Test that all mixins work together properly."""
        # Test BaseViewSet ordering
        self.assertEqual(self.viewset.ordering, ["id"])

        # Test SearchFilterMixin
        search_fields = self.viewset.get_search_fields()
        self.assertIsInstance(search_fields, list)

        filterset_fields = self.viewset.get_filterset_fields()
        self.assertIsInstance(filterset_fields, dict)

        # Test UserManagementMixin methods exist
        self.assertTrue(hasattr(self.viewset, "add_user"))
        self.assertTrue(hasattr(self.viewset, "remove_user"))
        self.assertTrue(hasattr(self.viewset, "add_admin"))
        self.assertTrue(hasattr(self.viewset, "remove_admin"))


@pytest.mark.django_db
class TestEdgeCasesAndErrorScenarios(TestCase):
    """Test edge cases and error scenarios."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="testuser", email="test@example.com")

    def test_baseviewset_with_none_queryset(self):
        """Test BaseViewSet behavior when queryset is None."""
        viewset = BaseViewSet()
        viewset.queryset = None

        request = self.factory.get("/")
        request.user = self.user
        viewset.request = request

        # Should raise AttributeError when trying to access queryset.model
        with self.assertRaises(AttributeError):
            viewset.get_queryset()

    def test_usermanagementmixin_with_invalid_field_name(self):
        """Test UserManagementMixin with invalid field name."""

        class TestViewSet(UserManagementMixin):
            def get_object(self):
                return User.objects.create_user(username="test", email="test@example.com")

        viewset = TestViewSet()
        # Create DRF request
        request = Mock()
        request.data = {"user_id": self.user.id}

        # Test with invalid field name that doesn't exist
        response = viewset._add_user_to_field(request, "nonexistent_field")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Check if response data has 'detail' key or different structure
        if "detail" in response.data:
            self.assertIn("Failed to add user", response.data["detail"])
        else:
            # Check for other possible structures
            response_str = str(response.data)
            self.assertIn("Failed to add user", response_str)

    def test_searchfiltermixin_with_model_meta_access(self):
        """Test SearchFilterMixin properly accesses model._meta.fields."""

        # Create a test viewset with the existing MockModelForSearch
        class TestViewSet(SearchFilterMixin):
            queryset = MockModelForSearch.objects.all()

        viewset = TestViewSet()

        # Test that the methods work with the existing model
        search_fields = viewset.get_search_fields()
        filterset_fields = viewset.get_filterset_fields()

        # Verify fields are detected correctly
        self.assertIsInstance(search_fields, list)
        self.assertIsInstance(filterset_fields, dict)

        # Should find at least some common fields in MockModelForSearch
        expected_in_search = ["name", "username", "email", "first_name", "last_name", "description"]
        for field in expected_in_search:
            self.assertIn(field, search_fields)

        expected_in_filter = ["name", "username", "email", "description"]
        for field in expected_in_filter:
            self.assertIn(field, filterset_fields)

    def test_handle_exception_with_different_exception_types(self):
        """Test handle_exception with different exception types."""
        viewset = BaseViewSet()

        # Test with different exception types
        exceptions = [
            ValueError("Value error"),
            KeyError("Key error"),
            AttributeError("Attribute error"),
            Exception("Generic exception"),
        ]

        for exc in exceptions:
            with patch.object(BaseViewSet.__bases__[1], "handle_exception") as mock_parent:
                mock_response = Response({"error": str(exc)}, status=400)
                mock_parent.return_value = mock_response

                result = viewset.handle_exception(exc)

                # Verify parent method was called and response returned
                mock_parent.assert_called_once_with(exc)
                self.assertEqual(result, mock_response)
