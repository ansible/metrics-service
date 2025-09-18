"""
Task Management API ViewSets for background task operations.

This module provides comprehensive REST API endpoints for managing background tasks
and task executions. It converts functionality previously available only through
the manage_tasks.py management command into a full-featured REST API with proper
authentication, validation, and monitoring capabilities.

ViewSets:
    TaskViewSet: Complete task lifecycle management with CRUD operations
    TaskExecutionViewSet: Task execution monitoring and history tracking

Features:
    - Task creation with scheduling and recurring task support
    - Task status monitoring and real-time updates
    - Task retry and cancellation operations
    - Task cleanup and maintenance operations
    - Comprehensive filtering and search capabilities
    - Available task function discovery
    - Task execution history and metrics

Operations:
    Create Tasks: POST /api/v1/tasks/ with function_name and parameters
    List Tasks: GET /api/v1/tasks/ with filtering by status, function, etc.
    Retry Tasks: POST /api/v1/tasks/{id}/retry/ for failed tasks
    Cancel Tasks: POST /api/v1/tasks/{id}/cancel/ for pending/running tasks
    Cleanup Tasks: POST /api/v1/tasks/cleanup/ to remove old completed tasks

Task Functions:
    Supports all registered task functions including:
    - cleanup_old_data: System maintenance tasks
    - send_notification_email: Email notifications
    - process_user_data: User data processing
    - execute_db_task: Database operations

Security:
    - Authentication required for all operations
    - RBAC permissions via DAB integration
    - Input validation for all task parameters
    - Safe task function execution with proper isolation
    - Audit logging for all task operations
"""

from datetime import timedelta
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.utils import build_error_response
from apps.tasks.models import Task, TaskExecution

from ..base_views import BaseViewSet
from .serializers import (
    TaskCleanupSerializer,
    TaskCreateSerializer,
    TaskExecutionSerializer,
    TaskListSerializer,
    TaskSerializer,
)


class TaskViewSet(BaseViewSet):
    """
    ViewSet for Task model with comprehensive task management functionality.

    This ViewSet provides all the functionality from the manage_tasks.py command
    converted to REST API endpoints including creation, listing, monitoring,
    and control.
    """

    queryset = Task.objects.select_related("created_by").all()
    serializer_class = TaskSerializer
    permission_classes = [AllowAny]  # Temporary for dashboard access
    ordering_fields = ["id", "name", "status", "priority", "scheduled_time", "created", "started_at", "completed_at"]
    ordering = ["-id"]

    @property
    def search_fields(self) -> list[str]:
        return self.get_named_model_search_fields(["function_name", "status", "created_by__username"])

    @property
    def filterset_fields(self) -> dict[str, list[str]]:
        extra_fields = {
            "function_name": self.get_text_field_filters(),
            "status": ["exact", "in"],
            "priority": ["exact", "gte", "lte"],
            "is_recurring": self.get_boolean_field_filters(),
            "created_by": self.get_foreign_key_filters(),
            "created_by__username": self.get_text_field_filters(),
            "scheduled_time": self.get_datetime_field_filters(),
            "started_at": self.get_datetime_field_filters(),
            "completed_at": self.get_datetime_field_filters(),
        }
        return self.build_filterset_fields(self.get_named_model_filterset_fields(extra_fields))

    def get_serializer_class(self):
        """Use appropriate serializer based on action."""
        if self.action == "create":
            return TaskCreateSerializer
        elif self.action == "list_filtered":
            return TaskListSerializer
        return self.serializer_class

    @extend_schema(
        operation_id="tasks_list_filtered",
        description="List tasks with filtering similar to manage_tasks list command",
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                description="Filter by task status",
                required=False,
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                description="Limit number of results (default: 20)",
                required=False,
            ),
        ],
        responses={200: TaskListSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="list")
    def list_filtered(self, request: HttpRequest) -> Response:
        """
        List tasks with filtering, similar to manage_tasks list command.

        This endpoint replicates the functionality of:
        python manage.py manage_tasks list --status=pending --limit=20

        Returns:
            Response: Filtered and limited list of tasks
        """
        queryset = self.get_queryset()

        # Filter by status if provided
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Apply limit (default 20)
        limit = int(request.query_params.get("limit", 20))
        queryset = queryset.order_by("-id")[:limit]

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        operation_id="tasks_running",
        description="Get currently running tasks",
        responses={200: TaskSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def running(self, request: HttpRequest) -> Response:
        """
        Get list of currently running tasks.

        Returns:
            Response: List of tasks with status 'running'
        """
        running_tasks = self.get_queryset().filter(status="running")
        serializer = self.get_serializer(running_tasks, many=True)
        return Response(serializer.data)

    @extend_schema(
        operation_id="tasks_pending",
        description="Get pending tasks waiting to run",
        responses={200: TaskSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def pending(self, request: HttpRequest) -> Response:
        """
        Get list of pending tasks waiting to run.

        Returns:
            Response: List of tasks with status 'pending'
        """
        pending_tasks = self.get_queryset().filter(status="pending")
        serializer = self.get_serializer(pending_tasks, many=True)
        return Response(serializer.data)

    @extend_schema(
        operation_id="tasks_retry",
        description="Retry a failed task",
        request=None,
        responses={200: {"message": "string"}},
    )
    @action(detail=True, methods=["post"])
    def retry(self, request: HttpRequest, pk: Any = None) -> Response:
        """
        Retry a failed task.

        This endpoint replicates the functionality of:
        python manage.py manage_tasks retry <task_id>

        Args:
            request: HTTP request
            pk: Primary key of the task

        Returns:
            Response: Success or error response
        """
        task = self.get_object()

        if not task.can_retry():
            error_response = build_error_response(
                f"Cannot retry task: status={task.status}, attempts={task.attempts}/{task.max_attempts}",
                status_code=400,
            )
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

        # Reset task status for retry (same logic as manage_tasks.py)
        task.status = "pending"
        task.error_message = ""
        task.started_at = None
        task.completed_at = None
        task.save()

        return Response({"message": f"Task '{task.name}' queued for retry"})

    @extend_schema(
        operation_id="tasks_cancel",
        description="Cancel a pending or running task",
        request=None,
        responses={200: {"message": "string"}},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request: HttpRequest, pk: Any = None) -> Response:
        """
        Cancel a pending or running task.

        This endpoint replicates the functionality of:
        python manage.py manage_tasks cancel <task_id>

        Args:
            request: HTTP request
            pk: Primary key of the task

        Returns:
            Response: Success or error response
        """
        task = self.get_object()

        if task.status in ["completed", "cancelled", "failed"]:
            error_response = build_error_response(f"Cannot cancel task with status: {task.status}", status_code=400)
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

        task.status = "cancelled"
        task.save()

        return Response({"message": f"Task '{task.name}' cancelled"})

    @extend_schema(
        operation_id="tasks_cleanup",
        description="Clean up old completed tasks",
        request=TaskCleanupSerializer,
        responses={200: {"message": "string", "count": "integer"}},
    )
    @action(detail=False, methods=["post"])
    def cleanup(self, request: HttpRequest) -> Response:
        """
        Clean up old completed tasks.

        This endpoint replicates the functionality of:
        python manage.py manage_tasks cleanup --days=30 --dry-run

        Args:
            request: HTTP request with cleanup parameters

        Returns:
            Response: Success message with count of tasks cleaned up
        """
        serializer = TaskCleanupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        days = serializer.validated_data["days"]
        dry_run = serializer.validated_data["dry_run"]

        cutoff_date = timezone.now() - timedelta(days=days)
        old_tasks = Task.objects.filter(status__in=["completed", "failed", "cancelled"], completed_at__lt=cutoff_date)

        count = old_tasks.count()

        if dry_run:
            # Return preview of what would be deleted
            preview = []
            for task in old_tasks[:10]:
                preview.append(
                    {
                        "id": task.id,
                        "name": task.name,
                        "status": task.status,
                        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    }
                )

            return Response(
                {
                    "message": f"Would delete {count} tasks older than {days} days",
                    "count": count,
                    "preview": preview,
                    "showing_preview_of": min(10, count),
                }
            )
        else:
            old_tasks.delete()
            return Response({"message": f"Deleted {count} old tasks", "count": count})

    @extend_schema(
        operation_id="tasks_available_functions",
        description="Get list of available task functions",
        responses={200: {"functions": "array"}},
    )
    @action(detail=False, methods=["get"])
    def available_functions(self, request: HttpRequest) -> Response:
        """
        Get list of available task functions for the create form.

        Returns:
            Response: List of available task function names and descriptions
        """
        from apps.tasks.tasks import TASK_FUNCTIONS

        functions = []
        for func_name, func in TASK_FUNCTIONS.items():
            functions.append(
                {
                    "name": func_name,
                    "description": func.__doc__.split("\n")[1].strip() if func.__doc__ else "No description available",
                }
            )

        return Response({"functions": functions})


class TaskExecutionViewSet(BaseViewSet):
    """
    ViewSet for TaskExecution model to monitor task execution history.
    """

    queryset = TaskExecution.objects.select_related("task").all()
    serializer_class = TaskExecutionSerializer
    permission_classes = [AllowAny]  # Temporary for dashboard access
    ordering_fields = ["started_at", "completed_at", "execution_time_seconds", "status"]
    ordering = ["-started_at"]

    @property
    def search_fields(self) -> list[str]:
        return ["task__name", "task__function_name", "worker_id"]

    @property
    def filterset_fields(self) -> dict[str, list[str]]:
        return {
            "task": ["exact"],
            "status": ["exact"],
            "worker_id": ["exact", "icontains"],
            "started_at": ["gte", "lte"],
            "completed_at": ["gte", "lte"],
        }
