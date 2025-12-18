"""
Comprehensive tests for apps/api/v1/tasks/views.py

This module provides extensive test coverage for task API views including
all HTTP methods, error conditions, filtering, and task operations.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import User
from apps.tasks.models import Task
from tests.base.task_test_base import TaskTestBase
from tests.test_utils import get_test_password


@pytest.mark.unit
@pytest.mark.django_db
class TestTaskViewSetAPI(TaskTestBase, APITestCase):
    """Test TaskViewSet API endpoints."""

    def setUp(self):
        """Set up test data."""
        # Call both parent setUp methods
        TaskTestBase.setUp(self)  # Creates self.user as regular user
        APITestCase.setUp(self)  # Sets up API client

        # Override self.user with superuser for API tests
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password=get_test_password()
        )

    def test_task_list_endpoint(self):
        """Test GET /api/v1/tasks/ endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create test tasks
        self.create_task(name="Task 1", function_name="cleanup_old_data", created_by=self.user, status="pending")
        self.create_task(
            name="Task 2", function_name="send_notification_email", created_by=self.user, status="completed"
        )

        url = reverse("tasks:v1:task-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 2

    def test_task_detail_endpoint(self):
        """Test GET /api/v1/tasks/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        task = self.create_task(
            name="Detail Task", function_name="cleanup_old_data", created_by=self.user, task_data={"days_old": 30}
        )

        url = reverse("tasks:v1:task-detail", kwargs={"pk": task.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Detail Task"
        assert response.data["function_name"] == "cleanup_old_data"
        assert response.data["task_data"]["days_old"] == 30

    def test_task_detail_not_found(self):
        """Test GET /api/v1/tasks/{invalid_id}/ returns 404."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-detail", kwargs={"pk": 99999})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_task_create_endpoint(self):
        """Test POST /api/v1/tasks/ endpoint."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-list")
        data = {"name": "New Task", "function_name": "cleanup_old_data", "task_data": {"days_old": 45}}
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Task"
        assert response.data["function_name"] == "cleanup_old_data"
        assert Task.objects.filter(name="New Task").exists()

    def test_task_create_with_scheduled_time(self):
        """Test creating task with scheduled time."""
        self.client.force_authenticate(user=self.user)

        future_time = timezone.now() + timedelta(hours=1)

        url = reverse("tasks:v1:task-list")
        data = {
            "name": "Scheduled Task",
            "function_name": "cleanup_old_data",
            "scheduled_time": future_time.isoformat(),
        }
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["scheduled_time"] is not None

    def test_task_create_invalid_data(self):
        """Test POST /api/v1/tasks/ with invalid data."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-list")
        data = {
            "name": "",  # Invalid empty name
            "function_name": "nonexistent_function",  # Invalid function
        }
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_task_create_missing_required_fields(self):
        """Test POST /api/v1/tasks/ with missing required fields."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-list")
        data = {
            "name": "Incomplete Task"
            # Missing function_name
        }
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_task_update_endpoint(self):
        """Test PUT /api/v1/tasks/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        task = self.create_task(name="Original Task", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("tasks:v1:task-detail", kwargs={"pk": task.pk})
        data = {"name": "Updated Task", "function_name": "cleanup_old_data", "task_data": {"days_old": 60}}
        response = self.client.put(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Task"
        assert response.data["task_data"]["days_old"] == 60

    def test_task_partial_update_endpoint(self):
        """Test PATCH /api/v1/tasks/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        task = self.create_task(name="Patch Task", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("tasks:v1:task-detail", kwargs={"pk": task.pk})
        data = {"name": "Patched Task"}
        response = self.client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Patched Task"
        # function_name should remain unchanged
        assert response.data["function_name"] == "cleanup_old_data"

    def test_task_delete_endpoint(self):
        """Test DELETE /api/v1/tasks/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        task = self.create_task(name="Delete Task", function_name="cleanup_old_data", created_by=self.user)
        task_id = task.pk

        url = reverse("tasks:v1:task-detail", kwargs={"pk": task_id})
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Task.objects.filter(pk=task_id).exists()

    def test_running_tasks_endpoint(self):
        """Test GET /api/v1/tasks/running/ endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create tasks with different statuses
        self.create_task(name="Running Task", function_name="cleanup_old_data", created_by=self.user, status="running")
        self.create_task(name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending")

        url = reverse("tasks:v1:task-running")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # All returned tasks should have "running" status
        for task in response.data:
            assert task["status"] == "running"

    def test_pending_tasks_endpoint(self):
        """Test GET /api/v1/tasks/pending/ endpoint."""
        self.client.force_authenticate(user=self.user)

        self.create_task(name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending")

        url = reverse("tasks:v1:task-pending")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # All returned tasks should have "pending" status
        for task in response.data:
            assert task["status"] == "pending"

    def test_task_retry_invalid_task(self):
        """Test retry endpoint with invalid task ID."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-retry", kwargs={"pk": 99999})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_task_cancel_invalid_task(self):
        """Test cancel endpoint with invalid task ID."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-cancel", kwargs={"pk": 99999})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.unit
@pytest.mark.django_db
class TestTaskExecutionViewSetAPI(TaskTestBase, APITestCase):
    """Test TaskExecutionViewSet API endpoints."""

    def setUp(self):
        """Set up test data."""
        # Call both parent setUp methods
        TaskTestBase.setUp(self)  # Creates self.user as regular user
        APITestCase.setUp(self)  # Sets up API client

        # Override self.user with superuser for API tests
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )

        self.task = self.create_task(name="Test Task", function_name="cleanup_old_data")
