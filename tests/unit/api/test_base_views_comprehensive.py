"""
Comprehensive tests for apps/api/v1/base_views.py to achieve 100% code coverage.
"""

from unittest.mock import Mock, patch

import pytest
from django.db import models
from django.test import TestCase
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from apps.api.v1.base_views import BaseViewSet
from apps.core.models import User


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
        self.assertEqual(len(viewset.permission_classes), 1)

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
