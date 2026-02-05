"""
Comprehensive tests for tasks/v1/urls.py

This module tests URL routing configuration for task API endpoints,
ensuring all URL patterns are properly registered and resolve correctly.
"""

import pytest
from django.test import TestCase
from django.urls import resolve, reverse
from rest_framework.routers import DefaultRouter

from apps.tasks.v1.urls import router
from apps.tasks.v1.views import TaskExecutionViewSet, TaskViewSet

# =============================================================================
# URL Pattern Registration Tests
# =============================================================================


@pytest.mark.unit
class TestURLConfiguration(TestCase):
    """Test URL configuration and router setup."""

    def test_router_is_default_router(self):
        """Test that the router is a DefaultRouter instance."""
        assert isinstance(router, DefaultRouter)

    def test_task_viewset_is_registered(self):
        """Test TaskViewSet is registered with the router."""
        # Check if TaskViewSet is in the router registry
        registered_viewsets = [reg[1] for reg in router.registry]
        assert TaskViewSet in registered_viewsets

    def test_task_execution_viewset_is_registered(self):
        """Test TaskExecutionViewSet is registered with the router."""
        # Check if TaskExecutionViewSet is in the router registry
        registered_viewsets = [reg[1] for reg in router.registry]
        assert TaskExecutionViewSet in registered_viewsets

    def test_task_viewset_basename(self):
        """Test TaskViewSet has correct basename."""
        # Find the TaskViewSet registration
        task_reg = next((reg for reg in router.registry if reg[1] == TaskViewSet), None)
        assert task_reg is not None
        assert task_reg[2] == "task"

    def test_task_execution_viewset_basename(self):
        """Test TaskExecutionViewSet has correct basename."""
        # Find the TaskExecutionViewSet registration
        exec_reg = next((reg for reg in router.registry if reg[1] == TaskExecutionViewSet), None)
        assert exec_reg is not None
        assert exec_reg[2] == "taskexecution"


# =============================================================================
# URL Reverse Resolution Tests
# =============================================================================


@pytest.mark.unit
class TestURLReverse(TestCase):
    """Test URL reverse resolution using Django's reverse() function."""

    def test_task_list_url_reverse(self):
        """Test task list URL can be reversed."""
        url = reverse("tasks:v1:task-list")
        assert url is not None
        assert "tasks" in url

    def test_task_detail_url_reverse(self):
        """Test task detail URL can be reversed with ID."""
        url = reverse("tasks:v1:task-detail", kwargs={"pk": 1})
        assert url is not None
        assert "tasks" in url
        assert "1" in url

    def test_task_running_url_reverse(self):
        """Test task running action URL can be reversed."""
        url = reverse("tasks:v1:task-running")
        assert url is not None
        assert "running" in url

    def test_task_pending_url_reverse(self):
        """Test task pending action URL can be reversed."""
        url = reverse("tasks:v1:task-pending")
        assert url is not None
        assert "pending" in url

    def test_task_retry_url_reverse(self):
        """Test task retry action URL can be reversed."""
        url = reverse("tasks:v1:task-retry", kwargs={"pk": 1})
        assert url is not None
        assert "retry" in url
        assert "1" in url

    def test_task_cancel_url_reverse(self):
        """Test task cancel action URL can be reversed."""
        url = reverse("tasks:v1:task-cancel", kwargs={"pk": 1})
        assert url is not None
        assert "cancel" in url
        assert "1" in url

    def test_task_execution_list_url_reverse(self):
        """Test task execution list URL can be reversed."""
        url = reverse("tasks:v1:taskexecution-list")
        assert url is not None
        assert "executions" in url

    def test_task_execution_detail_url_reverse(self):
        """Test task execution detail URL can be reversed."""
        url = reverse("tasks:v1:taskexecution-detail", kwargs={"pk": 1})
        assert url is not None
        assert "executions" in url
        assert "1" in url


# =============================================================================
# URL Pattern Matching Tests
# =============================================================================


@pytest.mark.unit
class TestURLPatternMatching(TestCase):
    """Test URL patterns match expected paths."""

    def test_task_list_url_pattern(self):
        """Test task list URL pattern matches expected path."""
        url = reverse("tasks:v1:task-list")
        # URL should end with /api/v1/tasks/
        assert url.endswith("/tasks/")

    def test_task_detail_url_pattern(self):
        """Test task detail URL pattern includes ID."""
        url = reverse("tasks:v1:task-detail", kwargs={"pk": 42})
        # URL should contain the ID
        assert "/42/" in url

    def test_task_execution_url_pattern(self):
        """Test task execution URL includes 'executions'."""
        url = reverse("tasks:v1:taskexecution-list")
        # URL should contain 'executions'
        assert "executions" in url


# =============================================================================
# URL Resolution Tests
# =============================================================================


@pytest.mark.unit
class TestURLResolution(TestCase):
    """Test URLs resolve to correct views."""

    def test_task_list_url_resolves_to_taskviewset(self):
        """Test task list URL resolves to TaskViewSet."""
        url = reverse("tasks:v1:task-list")
        resolved = resolve(url)
        assert resolved.func.cls == TaskViewSet

    def test_task_detail_url_resolves_to_taskviewset(self):
        """Test task detail URL resolves to TaskViewSet."""
        url = reverse("tasks:v1:task-detail", kwargs={"pk": 1})
        resolved = resolve(url)
        assert resolved.func.cls == TaskViewSet

    def test_task_running_url_resolves_to_taskviewset(self):
        """Test task running URL resolves to TaskViewSet."""
        url = reverse("tasks:v1:task-running")
        resolved = resolve(url)
        assert resolved.func.cls == TaskViewSet

    def test_task_execution_list_url_resolves_to_executionviewset(self):
        """Test task execution list URL resolves to TaskExecutionViewSet."""
        url = reverse("tasks:v1:taskexecution-list")
        resolved = resolve(url)
        assert resolved.func.cls == TaskExecutionViewSet

    def test_task_execution_detail_url_resolves_to_executionviewset(self):
        """Test task execution detail URL resolves to TaskExecutionViewSet."""
        url = reverse("tasks:v1:taskexecution-detail", kwargs={"pk": 1})
        resolved = resolve(url)
        assert resolved.func.cls == TaskExecutionViewSet


# =============================================================================
# URL Namespace Tests
# =============================================================================


@pytest.mark.unit
class TestURLNamespace(TestCase):
    """Test URL namespacing is correctly configured."""

    def test_app_name_is_tasks_v1(self):
        """Test app_name is set to 'tasks_v1'."""
        from apps.tasks.v1 import urls

        assert hasattr(urls, "app_name")
        assert urls.app_name == "tasks_v1"

    def test_task_urls_use_correct_namespace(self):
        """Test task URLs can be reversed with namespace."""
        # Should be accessible via tasks:v1:task-list
        url = reverse("tasks:v1:task-list")
        assert url is not None

    def test_all_task_urls_have_namespace(self):
        """Test all task URL names include the namespace."""
        # All URLs should be reversible with tasks:v1: prefix
        url_names = [
            "task-list",
            "task-detail",
            "task-running",
            "task-pending",
            "taskexecution-list",
            "taskexecution-detail",
        ]

        for name in url_names:
            url = reverse(f"tasks:v1:{name}", kwargs={"pk": 1} if "detail" in name else {})
            assert url is not None


# =============================================================================
# URL Action Tests
# =============================================================================


@pytest.mark.unit
class TestURLActions(TestCase):
    """Test custom action URLs are properly configured."""

    def test_running_action_is_list_action(self):
        """Test 'running' is a list-level action (no pk required)."""
        # Should not require pk
        url = reverse("tasks:v1:task-running")
        assert url is not None
        # URL should not contain a number
        import re

        assert not re.search(r"/\d+/", url)

    def test_pending_action_is_list_action(self):
        """Test 'pending' is a list-level action (no pk required)."""
        # Should not require pk
        url = reverse("tasks:v1:task-pending")
        assert url is not None
        # URL should not contain a number
        import re

        assert not re.search(r"/\d+/", url)

    def test_retry_action_is_detail_action(self):
        """Test 'retry' is a detail-level action (requires pk)."""
        # Should require pk
        url = reverse("tasks:v1:task-retry", kwargs={"pk": 123})
        assert url is not None
        # URL should contain the pk
        assert "123" in url

    def test_cancel_action_is_detail_action(self):
        """Test 'cancel' is a detail-level action (requires pk)."""
        # Should require pk
        url = reverse("tasks:v1:task-cancel", kwargs={"pk": 456})
        assert url is not None
        # URL should contain the pk
        assert "456" in url


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.unit
class TestURLIntegration(TestCase):
    """Integration tests for URL configuration."""

    def test_all_standard_rest_urls_exist(self):
        """Test all standard REST URLs exist."""
        # Standard REST endpoints that should exist
        endpoints = [
            ("tasks:v1:task-list", {}),  # GET, POST
            ("tasks:v1:task-detail", {"pk": 1}),  # GET, PUT, PATCH, DELETE
            ("tasks:v1:taskexecution-list", {}),
            ("tasks:v1:taskexecution-detail", {"pk": 1}),
        ]

        for url_name, kwargs in endpoints:
            url = reverse(url_name, kwargs=kwargs)
            assert url is not None
            # Each URL should resolve
            resolved = resolve(url)
            assert resolved is not None

    def test_all_custom_action_urls_exist(self):
        """Test all custom action URLs exist."""
        # Custom action endpoints
        actions = [
            ("tasks:v1:task-running", {}),
            ("tasks:v1:task-pending", {}),
            ("tasks:v1:task-retry", {"pk": 1}),
            ("tasks:v1:task-cancel", {"pk": 1}),
        ]

        for url_name, kwargs in actions:
            url = reverse(url_name, kwargs=kwargs)
            assert url is not None
            # Each URL should resolve
            resolved = resolve(url)
            assert resolved is not None

    def test_url_pattern_uniqueness(self):
        """Test URL patterns are unique (no conflicts)."""
        # Get all URL patterns
        task_list_url = reverse("tasks:v1:task-list")
        task_detail_url = reverse("tasks:v1:task-detail", kwargs={"pk": 1})
        execution_list_url = reverse("tasks:v1:taskexecution-list")

        # All URLs should be different
        urls = [task_list_url, task_detail_url, execution_list_url]
        assert len(urls) == len(set(urls))

    def test_router_generated_urls_count(self):
        """Test router generates expected number of URLs."""
        # Router should generate URLs for both viewsets
        assert len(router.registry) >= 2
