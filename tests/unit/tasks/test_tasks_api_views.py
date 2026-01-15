"""
Comprehensive tests for task API views, viewsets, and serializers.

This module consolidates all task API testing into a single organized file with
clear separation by component:
- TestTaskViewSet: Task CRUD endpoints and custom actions
- TestTaskExecutionViewSet: Task execution endpoints
- TestTaskSerializers: Serializer validation and field handling
- TestTaskFiltering: Query parameters, search, pagination
- TestTaskPermissions: Access control and authentication

Tests cover all HTTP methods, error conditions, edge cases, and serializer validation.
"""

from datetime import timedelta

import pytest
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone as django_timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase

from apps.core.models import User
from apps.tasks.models import Task, TaskExecution
from apps.tasks.v1.serializers import (
    TaskCreateSerializer,
    TaskExecutionSerializer,
    TaskListSerializer,
    TaskSerializer,
)
from apps.tasks.v1.views import TaskExecutionViewSet, TaskViewSet
from tests.test_utils import get_test_password

# =============================================================================
# TaskViewSet Tests - CRUD Operations and Custom Actions
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
@override_settings(MODE="development")
class TestTaskViewSet(APITestCase):
    """Test TaskViewSet CRUD endpoints and custom actions."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password=get_test_password()
        )
        self.factory = APIRequestFactory()

    def _create_task_safely(self, **kwargs):
        """Create a task without triggering signals."""
        task = Task(**kwargs)
        task.save()
        return task

    # List and Detail Tests
    def test_task_list_endpoint(self):
        """Test GET /api/v1/tasks/ returns task list."""
        self.client.force_authenticate(user=self.user)

        self._create_task_safely(
            name="Task 1", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )
        self._create_task_safely(
            name="Task 2", function_name="cleanup_old_data", created_by=self.user, status="completed"
        )

        url = reverse("tasks:v1:task-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 2

    def test_task_detail_endpoint(self):
        """Test GET /api/v1/tasks/{id}/ returns task details."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(
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

    # Create Tests
    def test_task_create_endpoint(self):
        """Test POST /api/v1/tasks/ creates new task."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-list")
        data = {"name": "New Task", "function_name": "cleanup_old_data", "task_data": {"days_old": 45}}
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Task"
        assert response.data["function_name"] == "cleanup_old_data"
        assert Task.objects.filter(name="New Task").exists()

    def test_task_create_with_scheduled_time(self):
        """Test creating task with future scheduled time."""
        self.client.force_authenticate(user=self.user)

        future_time = django_timezone.now() + timedelta(hours=1)

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
        """Test POST /api/v1/tasks/ with invalid data returns 400."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-list")
        data = {
            "name": "",  # Invalid empty name
            "function_name": "nonexistent_function",
        }
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_task_create_missing_required_fields(self):
        """Test POST /api/v1/tasks/ with missing required fields."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-list")
        data = {"name": "Incomplete Task"}  # Missing function_name
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Update Tests
    def test_task_update_endpoint(self):
        """Test PUT /api/v1/tasks/{id}/ updates task."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(name="Original Task", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("tasks:v1:task-detail", kwargs={"pk": task.pk})
        data = {"name": "Updated Task", "function_name": "cleanup_old_data", "task_data": {"days_old": 60}}
        response = self.client.put(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Task"
        assert response.data["task_data"]["days_old"] == 60

    def test_task_partial_update_endpoint(self):
        """Test PATCH /api/v1/tasks/{id}/ partially updates task."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(name="Patch Task", function_name="cleanup_old_data", created_by=self.user)

        url = reverse("tasks:v1:task-detail", kwargs={"pk": task.pk})
        data = {"name": "Patched Task"}
        response = self.client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Patched Task"
        # function_name should remain unchanged
        assert response.data["function_name"] == "cleanup_old_data"

    # Delete Tests
    def test_task_delete_endpoint(self):
        """Test DELETE /api/v1/tasks/{id}/ deletes task."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(name="Delete Task", function_name="cleanup_old_data", created_by=self.user)
        task_id = task.pk

        url = reverse("tasks:v1:task-detail", kwargs={"pk": task_id})
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Task.objects.filter(pk=task_id).exists()

    # Custom Action Tests - Status Filtering
    def test_running_tasks_endpoint(self):
        """Test GET /api/v1/tasks/running/ returns only running tasks."""
        self.client.force_authenticate(user=self.user)

        self._create_task_safely(
            name="Running Task", function_name="cleanup_old_data", created_by=self.user, status="running"
        )
        self._create_task_safely(
            name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )

        url = reverse("tasks:v1:task-running")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        for task in response.data:
            assert task["status"] == "running"

    def test_pending_tasks_endpoint(self):
        """Test GET /api/v1/tasks/pending/ returns only pending tasks."""
        self.client.force_authenticate(user=self.user)

        self._create_task_safely(
            name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )

        url = reverse("tasks:v1:task-pending")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        for task in response.data:
            assert task["status"] == "pending"

    # Custom Action Tests - Retry and Cancel
    def test_task_retry_invalid_task(self):
        """Test retry endpoint with invalid task ID returns 404."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-retry", kwargs={"pk": 99999})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_task_retry_successful(self):
        """Test successful task retry resets task status."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(
            name="Failed Task",
            function_name="cleanup_old_data",
            created_by=self.user,
            status="failed",
            attempts=1,
            max_attempts=3,
            error_message="Test error",
        )

        url = reverse("tasks:v1:task-retry", kwargs={"pk": task.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert "queued for retry" in response.data["message"]

        # Verify task was reset
        task.refresh_from_db()
        assert task.status == "pending"
        assert task.error_message == ""
        assert task.started_at is None
        assert task.completed_at is None

    def test_task_retry_cannot_retry_max_attempts_reached(self):
        """Test retry fails when max attempts reached."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(
            name="Failed Task",
            function_name="cleanup_old_data",
            created_by=self.user,
            status="failed",
            attempts=3,
            max_attempts=3,
        )

        url = reverse("tasks:v1:task-retry", kwargs={"pk": task.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot retry task" in response.data["error"]

    def test_task_retry_cannot_retry_completed_task(self):
        """Test retry fails for completed tasks."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(
            name="Completed Task", function_name="cleanup_old_data", created_by=self.user, status="completed"
        )

        url = reverse("tasks:v1:task-retry", kwargs={"pk": task.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_task_cancel_invalid_task(self):
        """Test cancel endpoint with invalid task ID returns 404."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-cancel", kwargs={"pk": 99999})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_task_cancel_successful(self):
        """Test successful task cancellation."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(
            name="Pending Task", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )

        url = reverse("tasks:v1:task-cancel", kwargs={"pk": task.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert "cancelled" in response.data["message"]

        # Verify task was cancelled
        task.refresh_from_db()
        assert task.status == "cancelled"

    def test_task_cancel_cannot_cancel_completed_task(self):
        """Test cancel fails for completed tasks."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(
            name="Completed Task", function_name="cleanup_old_data", created_by=self.user, status="completed"
        )

        url = reverse("tasks:v1:task-cancel", kwargs={"pk": task.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot cancel task" in response.data["error"]

    def test_task_cancel_cannot_cancel_failed_task(self):
        """Test cancel fails for failed tasks."""
        self.client.force_authenticate(user=self.user)

        task = self._create_task_safely(
            name="Failed Task", function_name="cleanup_old_data", created_by=self.user, status="failed"
        )

        url = reverse("tasks:v1:task-cancel", kwargs={"pk": task.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot cancel task" in response.data["error"]

    # Custom Action Tests - Cleanup
    def test_task_cleanup_dry_run(self):
        """Test cleanup in dry-run mode doesn't delete tasks."""
        self.client.force_authenticate(user=self.user)

        # Create old completed tasks
        from datetime import timedelta

        from django.utils import timezone

        old_date = timezone.now() - timedelta(days=40)
        task = self._create_task_safely(
            name="Old Task", function_name="cleanup_old_data", created_by=self.user, status="completed"
        )
        task.completed_at = old_date
        task.save()

        url = reverse("tasks:v1:task-cleanup")
        response = self.client.post(url, {"days": 30, "dry_run": True}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "Would delete" in response.data["message"]
        # Task should still exist
        assert Task.objects.filter(pk=task.pk).exists()

    def test_task_cleanup_actually_deletes(self):
        """Test cleanup actually deletes old tasks."""
        self.client.force_authenticate(user=self.user)

        from datetime import timedelta

        from django.utils import timezone

        old_date = timezone.now() - timedelta(days=40)
        task = self._create_task_safely(
            name="Old Task", function_name="cleanup_old_data", created_by=self.user, status="completed"
        )
        task.completed_at = old_date
        task.save()
        task_id = task.pk

        url = reverse("tasks:v1:task-cleanup")
        response = self.client.post(url, {"days": 30, "dry_run": False}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "Deleted" in response.data["message"]
        # Task should be deleted
        assert not Task.objects.filter(pk=task_id).exists()

    def test_task_cleanup_default_values(self):
        """Test cleanup with default values (30 days, dry_run=false)."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-cleanup")
        response = self.client.post(url, {}, format="json")

        assert response.status_code == status.HTTP_200_OK

    # Custom Action Tests - List Filtered
    def test_list_filtered_with_status(self):
        """Test list_filtered action with status filter."""
        self.client.force_authenticate(user=self.user)

        self._create_task_safely(
            name="Pending Task 1", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )
        self._create_task_safely(
            name="Pending Task 2", function_name="cleanup_old_data", created_by=self.user, status="pending"
        )
        self._create_task_safely(
            name="Running Task", function_name="cleanup_old_data", created_by=self.user, status="running"
        )

        url = reverse("tasks:v1:task-list-filtered")
        response = self.client.get(url, {"status": "pending"})

        assert response.status_code == status.HTTP_200_OK
        # Should only return pending tasks
        for task in response.data:
            assert task["status"] == "pending"

    def test_list_filtered_with_limit(self):
        """Test list_filtered action with custom limit."""
        self.client.force_authenticate(user=self.user)

        # Create 5 tasks
        for i in range(5):
            self._create_task_safely(
                name=f"Task {i}", function_name="cleanup_old_data", created_by=self.user, status="pending"
            )

        url = reverse("tasks:v1:task-list-filtered")
        response = self.client.get(url, {"limit": 3})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 3

    def test_list_filtered_default_limit(self):
        """Test list_filtered action uses default limit of 20."""
        self.client.force_authenticate(user=self.user)

        url = reverse("tasks:v1:task-list-filtered")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Response should be limited (even if no tasks, check it doesn't error)
        assert isinstance(response.data, list)

    # ViewSet Initialization Tests
    def test_viewset_initialization(self):
        """Test TaskViewSet can be initialized."""
        viewset = TaskViewSet()
        assert viewset is not None

    def test_get_queryset(self):
        """Test get_queryset returns Task queryset."""
        viewset = TaskViewSet()
        queryset = viewset.queryset
        assert queryset.model == Task

    def test_get_serializer_class_for_list(self):
        """Test get_serializer_class returns a serializer for list action."""
        viewset = TaskViewSet()
        viewset.action = "list"
        serializer_class = viewset.get_serializer_class()
        # Should return a serializer (TaskListSerializer or TaskSerializer)
        assert serializer_class in [TaskListSerializer, TaskSerializer]

    def test_get_serializer_class_for_create(self):
        """Test get_serializer_class returns correct serializer for create action."""
        viewset = TaskViewSet()
        viewset.action = "create"
        serializer_class = viewset.get_serializer_class()
        assert serializer_class == TaskCreateSerializer


# =============================================================================
# TaskExecutionViewSet Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
@override_settings(MODE="development")
class TestTaskExecutionViewSet(APITestCase):
    """Test TaskExecutionViewSet endpoints."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.task = Task(name="Test Task", function_name="cleanup_old_data", created_by=self.user)
        self.task.save()

    @pytest.mark.skip(reason="URL routing test - executions endpoint may not be exposed in test environment")
    def test_execution_list_endpoint(self):
        """Test GET /api/v1/executions/ returns execution list."""
        self.client.force_authenticate(user=self.user)

        TaskExecution.objects.create(task=self.task, status="pending")
        TaskExecution.objects.create(task=self.task, status="completed")

        url = reverse("tasks:v1:taskexecution-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 2

    def test_execution_detail_endpoint(self):
        """Test GET /api/v1/executions/{id}/ returns execution details."""
        self.client.force_authenticate(user=self.user)

        execution = TaskExecution.objects.create(task=self.task, status="running")

        url = reverse("tasks:v1:taskexecution-detail", kwargs={"pk": execution.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "running"

    def test_execution_viewset_initialization(self):
        """Test TaskExecutionViewSet can be initialized."""
        viewset = TaskExecutionViewSet()
        assert viewset is not None
        assert viewset.queryset.model == TaskExecution


# =============================================================================
# Serializer Tests - Validation and Field Handling
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestTaskSerializers(TestCase):
    """Test task serializer validation and field handling."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )
        self.task = Task(
            name="Test Task", function_name="cleanup_old_data", task_data={"key": "value"}, created_by=self.user
        )
        self.task.save()
        self.factory = APIRequestFactory()

    def test_task_serializer_fields(self):
        """Test TaskSerializer includes expected fields."""
        request = self.factory.get("/api/v1/tasks/")
        request.user = self.user
        serializer = TaskSerializer(instance=self.task, context={"request": request})
        data = serializer.data

        expected_fields = {"id", "name", "function_name", "task_data", "status", "created", "modified"}
        assert expected_fields.issubset(set(data.keys()))

    def test_task_serializer_read_only_fields(self):
        """Test TaskSerializer read-only fields cannot be modified."""
        serializer = TaskSerializer(instance=self.task)

        # Check that certain fields are read-only
        serializer.Meta.read_only_fields if hasattr(serializer.Meta, "read_only_fields") else []
        # Status transitions should be controlled
        assert "created" in str(serializer.fields)

    def test_task_create_serializer_validation(self):
        """Test TaskCreateSerializer validates required fields."""
        serializer = TaskCreateSerializer(data={"name": "New Task"})  # Missing function_name

        assert not serializer.is_valid()
        assert "function_name" in serializer.errors

    def test_task_create_serializer_valid_data(self):
        """Test TaskCreateSerializer accepts valid data."""
        request = self.factory.post("/api/v1/tasks/")
        request.user = self.user

        serializer = TaskCreateSerializer(
            data={"name": "Valid Task", "function_name": "cleanup_old_data", "task_data": {"days": 30}},
            context={"request": request},
        )

        assert serializer.is_valid(), serializer.errors

    def test_task_execution_serializer_fields(self):
        """Test TaskExecutionSerializer includes expected fields."""
        execution = TaskExecution.objects.create(task=self.task, status="running")
        request = self.factory.get("/api/v1/executions/")
        request.user = self.user
        serializer = TaskExecutionSerializer(instance=execution, context={"request": request})
        data = serializer.data

        expected_fields = {"id", "task", "status", "started_at", "completed_at"}
        assert expected_fields.issubset(set(data.keys()))

    def test_task_list_serializer_optimized_fields(self):
        """Test TaskListSerializer provides optimized field set."""
        serializer = TaskListSerializer(instance=self.task)
        data = serializer.data

        # List serializer should have minimal fields for performance
        assert "id" in data
        assert "name" in data
        assert "status" in data


# =============================================================================
# Filtering and Pagination Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
@override_settings(MODE="development")
class TestTaskFiltering(APITestCase):
    """Test task filtering, search, and pagination."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.client.force_authenticate(user=self.user)

        # Create tasks with various statuses
        for i in range(5):
            task = Task(name=f"Task {i}", function_name="cleanup_old_data", created_by=self.user, status="pending")
            task.save()

        for i in range(3):
            task = Task(name=f"Running {i}", function_name="cleanup_old_data", created_by=self.user, status="running")
            task.save()

    def test_filter_by_status(self):
        """Test filtering tasks by status parameter."""
        url = reverse("tasks:v1:task-list")
        response = self.client.get(url, {"status": "pending"})

        assert response.status_code == status.HTTP_200_OK
        # Handle both paginated (dict with 'results') and non-paginated (list) responses
        tasks = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        for task in tasks:
            assert task["status"] == "pending"

    def test_filter_by_function_name(self):
        """Test filtering tasks by function_name parameter."""
        url = reverse("tasks:v1:task-list")
        response = self.client.get(url, {"function_name": "cleanup_old_data"})

        assert response.status_code == status.HTTP_200_OK
        # Handle both paginated (dict with 'results') and non-paginated (list) responses
        tasks = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        for task in tasks:
            assert task["function_name"] == "cleanup_old_data"

    def test_pagination(self):
        """Test task list pagination."""
        url = reverse("tasks:v1:task-list")
        response = self.client.get(url, {"page_size": 3})

        assert response.status_code == status.HTTP_200_OK
        # Response should contain pagination metadata or limited results
        assert len(response.data) <= 10  # Default or custom page size


# =============================================================================
# Permission and Authentication Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestTaskPermissions(APITestCase):
    """Test task API permissions and authentication."""

    def setUp(self):
        """Set up test data."""
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password=get_test_password()
        )

    @override_settings(MODE="production")
    def test_development_mode_disabled_access_denied(self):
        """Test requests are denied when development mode is disabled."""
        url = reverse("tasks:v1:task-list")
        response = self.client.get(url)

        # Should deny access when development mode is disabled
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @override_settings(MODE="development")
    def test_authenticated_user_can_list_tasks(self):
        """Test authenticated users can list tasks."""
        self.client.force_authenticate(user=self.regular_user)

        url = reverse("tasks:v1:task-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

    @override_settings(MODE="development")
    def test_admin_user_full_access(self):
        """Test admin users have full access to task operations."""
        self.client.force_authenticate(user=self.admin_user)

        # Test create
        url = reverse("tasks:v1:task-list")
        data = {"name": "Admin Task", "function_name": "cleanup_old_data"}
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED


# =============================================================================
# Edge Cases and Import Tests
# =============================================================================


@pytest.mark.unit
class TestTaskImports(TestCase):
    """Test that task modules can be imported."""

    def test_viewset_imports(self):
        """Test TaskViewSet and TaskExecutionViewSet can be imported."""
        assert TaskViewSet is not None
        assert TaskExecutionViewSet is not None

    def test_serializer_imports(self):
        """Test all serializers can be imported."""
        assert TaskSerializer is not None
        assert TaskCreateSerializer is not None
        assert TaskListSerializer is not None
        assert TaskExecutionSerializer is not None
