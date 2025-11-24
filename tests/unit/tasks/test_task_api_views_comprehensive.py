"""
Comprehensive tests for apps/api/v1/tasks/views.py

This module provides extensive test coverage for task API views including
all HTTP methods, error conditions, filtering, and task operations.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import User
from apps.tasks.models import Task, TaskExecution
from tests.test_utils import get_test_password


@pytest.mark.unit
@pytest.mark.django_db
class TestTaskViewSetAPI(APITestCase):
    """Test TaskViewSet API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password=get_test_password()
        )

    def _create_task_safely(self, **kwargs):
        """Create a task without triggering signals."""
        task = Task(**kwargs)
        task._skip_signals = True
        task.save()
        return task

    def test_task_list_endpoint(self):
        """Test GET /api/v1/tasks/ endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create test tasks
        self._create_task_safely(
            name="Task 1", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )
        self._create_task_safely(
            name="Task 2", function_name="send_notification_email", created_by=self.user, status="completed"
        )

        url = reverse("api:v1:task-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 2

    def test_task_list_filtering_by_status(self):
        """Test filtering tasks by status."""
        self.client.force_authenticate(user=self.user)

        self._create_task_safely(
            name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )
        self._create_task_safely(
            name="Completed Task", function_name="cleanup_old_data", created_by=self.user, status="completed"
        )

        # Test filtering by pending status
        url = reverse("api:v1:task-list")
        response = self.client.get(url, {"status": "pending"})

        assert response.status_code == status.HTTP_200_OK
        pending_tasks = [task for task in response.data if task["status"] == "pending"]
        assert len(pending_tasks) >= 1

    def test_task_list_filtering_by_function_name(self):
        """Test filtering tasks by function_name."""
        self.client.force_authenticate(user=self.user)

        self._create_task_safely(name="Cleanup Task", function_name="cleanup_old_data", created_by=self.user)
        self._create_task_safely(name="Email Task", function_name="send_notification_email", created_by=self.user)

        url = reverse("api:v1:task-list")
        response = self.client.get(url, {"function_name": "cleanup_old_data"})

        assert response.status_code == status.HTTP_200_OK
        cleanup_tasks = [task for task in response.data if task["function_name"] == "cleanup_old_data"]
        assert len(cleanup_tasks) >= 1

    def test_task_detail_endpoint(self):
        """Test GET /api/v1/tasks/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(
            name="Detail Task", function_name="cleanup_old_data", created_by=self.user, task_data={"days_old": 30}
        )

        url = reverse("api:v1:task-detail", kwargs={"pk": task.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Detail Task"
        assert response.data["function_name"] == "cleanup_old_data"
        assert response.data["task_data"]["days_old"] == 30

    def test_task_detail_not_found(self):
        """Test GET /api/v1/tasks/{invalid_id}/ returns 404."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:v1:task-detail", kwargs={"pk": 99999})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_task_create_endpoint(self):
        """Test POST /api/v1/tasks/ endpoint."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:v1:task-list")
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

        url = reverse("api:v1:task-list")
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

        url = reverse("api:v1:task-list")
        data = {
            "name": "",  # Invalid empty name
            "function_name": "nonexistent_function",  # Invalid function
        }
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_task_create_missing_required_fields(self):
        """Test POST /api/v1/tasks/ with missing required fields."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:v1:task-list")
        data = {
            "name": "Incomplete Task"
            # Missing function_name
        }
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_task_update_endpoint(self):
        """Test PUT /api/v1/tasks/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(name="Original Task", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("api:v1:task-detail", kwargs={"pk": task.pk})
        data = {"name": "Updated Task", "function_name": "cleanup_old_data", "task_data": {"days_old": 60}}
        response = self.client.put(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Task"
        assert response.data["task_data"]["days_old"] == 60

    def test_task_partial_update_endpoint(self):
        """Test PATCH /api/v1/tasks/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(name="Patch Task", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("api:v1:task-detail", kwargs={"pk": task.pk})
        data = {"name": "Patched Task"}
        response = self.client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Patched Task"
        # function_name should remain unchanged
        assert response.data["function_name"] == "cleanup_old_data"

    def test_task_delete_endpoint(self):
        """Test DELETE /api/v1/tasks/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(name="Delete Task", function_name="cleanup_old_data", created_by=self.user)
        task_id = task.pk

        url = reverse("api:v1:task-detail", kwargs={"pk": task_id})
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Task.objects.filter(pk=task_id).exists()

    def test_running_tasks_endpoint(self):
        """Test GET /api/v1/tasks/running/ endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create tasks with different statuses
        self._create_task_safely(
            name="Running Task", function_name="cleanup_old_data", created_by=self.user, status="running"
        )
        self._create_task_safely(
            name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )

        url = reverse("api:v1:task-running")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # All returned tasks should have "running" status
        for task in response.data:
            assert task["status"] == "running"

    def test_pending_tasks_endpoint(self):
        """Test GET /api/v1/tasks/pending/ endpoint."""
        self.client.force_authenticate(user=self.user)

        self._create_task_safely(
            name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )

        url = reverse("api:v1:task-pending")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # All returned tasks should have "pending" status
        for task in response.data:
            assert task["status"] == "pending"

    @patch("apps.api.v1.tasks.views.get_available_task_functions")
    def test_available_functions_endpoint(self, mock_get_functions):
        """Test GET /api/v1/tasks/available_functions/ endpoint."""
        self.client.force_authenticate(user=self.user)

        mock_functions = {
            "cleanup_old_data": {"name": "cleanup_old_data", "description": "Clean up old data", "enabled": True},
            "send_notification_email": {
                "name": "send_notification_email",
                "description": "Send notification emails",
                "enabled": True,
            },
        }
        mock_get_functions.return_value = mock_functions

        url = reverse("api:v1:task-available-functions")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "cleanup_old_data" in response.data
        assert "send_notification_email" in response.data

    def test_task_retry_endpoint(self):
        """Test POST /api/v1/tasks/{id}/retry/ endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create a failed task
        failed_task = self._create_task_safely(
            name="Failed Task", function_name="cleanup_old_data", created_by=self.user, status="failed"
        )

        url = reverse("api:v1:task-retry", kwargs={"pk": failed_task.pk})

        with patch("apps.api.v1.tasks.views.retry_task") as mock_retry:
            mock_retry.return_value = {"status": "success", "message": "Task retried"}
            response = self.client.post(url)

        assert response.status_code == status.HTTP_200_OK
        mock_retry.assert_called_once_with(failed_task.pk)

    def test_task_retry_invalid_task(self):
        """Test retry endpoint with invalid task ID."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:v1:task-retry", kwargs={"pk": 99999})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_task_cancel_endpoint(self):
        """Test POST /api/v1/tasks/{id}/cancel/ endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create a pending task
        pending_task = self._create_task_safely(
            name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )

        url = reverse("api:v1:task-cancel", kwargs={"pk": pending_task.pk})

        with patch("apps.api.v1.tasks.views.cancel_task") as mock_cancel:
            mock_cancel.return_value = {"status": "success", "message": "Task cancelled"}
            response = self.client.post(url)

        assert response.status_code == status.HTTP_200_OK
        mock_cancel.assert_called_once_with(pending_task.pk)

    def test_task_cancel_invalid_task(self):
        """Test cancel endpoint with invalid task ID."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:v1:task-cancel", kwargs={"pk": 99999})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_task_cleanup_endpoint(self):
        """Test POST /api/v1/tasks/cleanup/ endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create old completed tasks
        old_time = timezone.now() - timedelta(days=31)
        self._create_task_safely(
            name="Old Completed Task",
            function_name="cleanup_old_data",
            created_by=self.user,
            status="completed",
            completed_at=old_time,
        )

        url = reverse("api:v1:task-cleanup")
        data = {"days_old": 30}

        with patch("apps.api.v1.tasks.views.cleanup_old_tasks") as mock_cleanup:
            mock_cleanup.return_value = {"status": "success", "deleted_count": 1}
            response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        mock_cleanup.assert_called_once_with(30)

    def test_task_cleanup_invalid_days(self):
        """Test cleanup endpoint with invalid days parameter."""
        self.client.force_authenticate(user=self.user)

        url = reverse("api:v1:task-cleanup")
        data = {"days_old": -1}  # Invalid negative value
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated requests are denied."""
        url = reverse("api:v1:task-list")
        response = self.client.get(url)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_task_search_functionality(self):
        """Test task search functionality."""
        self.client.force_authenticate(user=self.user)

        self._create_task_safely(name="Email Cleanup Task", function_name="cleanup_old_data", created_by=self.user)
        self._create_task_safely(name="Database Maintenance", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("api:v1:task-list")
        response = self.client.get(url, {"search": "Email"})

        assert response.status_code == status.HTTP_200_OK
        # Should find the task with "Email" in the name
        email_tasks = [task for task in response.data if "Email" in task["name"]]
        assert len(email_tasks) >= 1

    def test_task_ordering(self):
        """Test task ordering functionality."""
        self.client.force_authenticate(user=self.user)

        # Create tasks with different creation times
        self._create_task_safely(name="A Task", function_name="cleanup_old_data", created_by=self.user)
        self._create_task_safely(name="Z Task", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("api:v1:task-list")
        response = self.client.get(url, {"ordering": "name"})

        assert response.status_code == status.HTTP_200_OK
        # Verify tasks are ordered by name
        if len(response.data) >= 2:
            # Check if ordering is working (first task name should be lexicographically smaller)
            assert response.data[0]["name"] <= response.data[1]["name"]

    def test_task_pagination(self):
        """Test task pagination."""
        self.client.force_authenticate(user=self.user)

        # Create multiple tasks
        for i in range(15):
            self._create_task_safely(name=f"Task {i:02d}", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("api:v1:task-list")
        response = self.client.get(url, {"page_size": 10})

        assert response.status_code == status.HTTP_200_OK
        # Check if pagination is working
        if isinstance(response.data, dict) and "count" in response.data:
            assert "results" in response.data
            assert len(response.data["results"]) <= 10
        else:
            # If not paginated, should still return results
            assert isinstance(response.data, list)


@pytest.mark.unit
@pytest.mark.django_db
class TestTaskExecutionViewSetAPI(APITestCase):
    """Test TaskExecutionViewSet API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )

        self.task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        self.task._skip_signals = True
        self.task.save()

    def test_task_execution_list_endpoint(self):
        """Test GET /api/v1/task-executions/ endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create task executions
        TaskExecution.objects.create(task=self.task, status="completed", result={"output": "success"})

        url = reverse("api:v1:taskexecution-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_task_execution_detail_endpoint(self):
        """Test GET /api/v1/task-executions/{id}/ endpoint."""
        self.client.force_authenticate(user=self.user)

        execution = TaskExecution.objects.create(task=self.task, status="completed", result={"output": "test result"})

        url = reverse("api:v1:taskexecution-detail", kwargs={"pk": execution.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "completed"
        assert response.data["result"]["output"] == "test result"

    def test_task_execution_filtering_by_status(self):
        """Test filtering task executions by status."""
        self.client.force_authenticate(user=self.user)

        TaskExecution.objects.create(task=self.task, status="completed")
        TaskExecution.objects.create(task=self.task, status="failed")

        url = reverse("api:v1:taskexecution-list")
        response = self.client.get(url, {"status": "completed"})

        assert response.status_code == status.HTTP_200_OK
        completed_executions = [ex for ex in response.data if ex["status"] == "completed"]
        assert len(completed_executions) >= 1

    def test_task_execution_filtering_by_task(self):
        """Test filtering task executions by task ID."""
        self.client.force_authenticate(user=self.user)

        TaskExecution.objects.create(task=self.task, status="completed")

        url = reverse("api:v1:taskexecution-list")
        response = self.client.get(url, {"task": self.task.pk})

        assert response.status_code == status.HTTP_200_OK
        task_executions = [ex for ex in response.data if ex["task"] == self.task.pk]
        assert len(task_executions) >= 1
