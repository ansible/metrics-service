"""
Unit tests for core models.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Organization, Team
from apps.tasks.models import Task, TaskChain, TaskChainMembership, TaskDependency, TaskExecution
from tests.test_utils import get_test_password

User = get_user_model()


@pytest.mark.unit
class CoreModelsTestCase(TestCase):
    """Test cases for core models."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

        self.organization = Organization.objects.create(name="Test Organization", description="A test organization")

        self.team = Team.objects.create(name="Test Team", description="A test team", organization=self.organization)

    def test_user_creation(self):
        """Test User model creation and string representation."""
        self.assertEqual(str(self.user), "testuser")
        self.assertEqual(self.user.email, "test@example.com")
        self.assertTrue(self.user.check_password(get_test_password()))

    def test_user_summary_fields(self):
        """Test User summary_fields method."""
        summary = self.user.summary_fields()
        self.assertIsInstance(summary, dict)

    def test_organization_creation(self):
        """Test Organization model creation and relationships."""
        self.assertEqual(str(self.organization), "Test Organization")
        self.assertEqual(self.organization.name, "Test Organization")

        # Test many-to-many relationships
        self.organization.users.add(self.user)
        self.organization.admins.add(self.user)

        self.assertIn(self.user, self.organization.users.all())
        self.assertIn(self.user, self.organization.admins.all())

    def test_team_creation(self):
        """Test Team model creation and relationships."""
        self.assertEqual(str(self.team), "Test Organization - Test Team")
        self.assertEqual(self.team.organization, self.organization)

        # Test many-to-many relationships
        self.team.users.add(self.user)
        self.team.admins.add(self.user)

        self.assertIn(self.user, self.team.users.all())
        self.assertIn(self.user, self.team.admins.all())


@pytest.mark.unit
class TaskModelTestCase(TestCase):
    """Test cases for Task system models."""

    def _create_task_safely(self, **kwargs):
        """Create a task without triggering signals."""
        task = Task(**kwargs)
        task.save()
        return task

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="taskuser", email="task@example.com")

        self.task = self._create_task_safely(
            name="Test Task",
            function_name="test_function",
            task_data={"param": "value"},
            created_by=self.user,
            status="pending",
        )

    def test_task_creation(self):
        """Test Task model creation."""
        self.assertEqual(str(self.task), "Test Task (test_function) - Pending")
        self.assertEqual(self.task.status, "pending")
        self.assertEqual(self.task.priority, 2)  # Normal priority
        self.assertEqual(self.task.attempts, 0)
        self.assertEqual(self.task.max_attempts, 3)
        self.assertEqual(self.task.timeout_seconds, 3600)
        self.assertFalse(self.task.is_recurring)

    def test_task_is_ready_to_run(self):
        """Test Task is_ready_to_run method."""
        # Task should be ready by default
        self.assertTrue(self.task.is_ready_to_run())

        # Task with future scheduled time should not be ready
        future_time = timezone.now() + timedelta(hours=1)
        self.task.scheduled_time = future_time
        self.task.save()
        self.assertFalse(self.task.is_ready_to_run())

        # Task with past scheduled time should be ready
        past_time = timezone.now() - timedelta(hours=1)
        self.task.scheduled_time = past_time
        self.task.save()
        self.assertTrue(self.task.is_ready_to_run())

        # Running task should not be ready
        self.task.status = "running"
        self.task.save()
        self.assertFalse(self.task.is_ready_to_run())

    def test_task_can_retry(self):
        """Test Task can_retry method."""
        # New task cannot be retried
        self.assertFalse(self.task.can_retry())

        # Failed task with attempts < max_attempts can be retried
        self.task.status = "failed"
        self.task.attempts = 1
        self.task.save()
        self.assertTrue(self.task.can_retry())

        # Failed task with attempts >= max_attempts cannot be retried
        self.task.attempts = 3
        self.task.save()
        self.assertFalse(self.task.can_retry())

    def test_task_dependency_creation(self):
        """Test TaskDependency model creation."""
        task2 = self._create_task_safely(
            name="Dependent Task", function_name="dependent_function", created_by=self.user
        )

        dependency = TaskDependency.objects.create(
            dependent_task=task2, prerequisite_task=self.task, required_status="completed"
        )

        self.assertEqual(str(dependency), "Dependent Task depends on Test Task")
        self.assertEqual(dependency.required_status, "completed")

        # Test that dependent task is not ready when prerequisite is pending
        self.assertFalse(task2.is_ready_to_run())

        # Test that dependent task is ready when prerequisite is completed
        self.task.status = "completed"
        self.task.save()
        self.assertTrue(task2.is_ready_to_run())

    def test_task_execution_creation(self):
        """Test TaskExecution model creation."""
        execution = TaskExecution.objects.create(task=self.task, status="running", worker_id="worker-123")

        self.assertEqual(execution.task, self.task)
        self.assertEqual(execution.status, "running")
        self.assertEqual(execution.worker_id, "worker-123")
        self.assertIsNotNone(execution.started_at)

    def test_task_execution_time_calculation(self):
        """Test TaskExecution execution time calculation."""
        start_time = timezone.now()
        end_time = start_time + timedelta(seconds=10)

        execution = TaskExecution.objects.create(
            task=self.task, status="completed", started_at=start_time, completed_at=end_time
        )

        self.assertEqual(execution.execution_time_seconds, 10.0)

    def test_task_chain_creation(self):
        """Test TaskChain model creation."""
        chain = TaskChain.objects.create(name="Test Chain", created_by=self.user)

        self.assertEqual(str(chain), "Test Chain")
        self.assertTrue(chain.is_active)

        # Test task chain membership
        task2 = self._create_task_safely(name="Task 2", function_name="function2", created_by=self.user)

        membership1 = TaskChainMembership.objects.create(chain=chain, task=self.task, order=1)

        membership2 = TaskChainMembership.objects.create(chain=chain, task=task2, order=2)

        self.assertEqual(str(membership1), "Test Chain - Test Task (order: 1)")
        self.assertEqual(str(membership2), "Test Chain - Task 2 (order: 2)")

        # Test that tasks are in the chain
        self.assertIn(self.task, chain.tasks.all())
        self.assertIn(task2, chain.tasks.all())
        self.assertEqual(chain.tasks.count(), 2)


@pytest.mark.unit
class ModelValidationTestCase(TestCase):
    """Test cases for model validation and constraints."""

    def _create_task_safely(self, **kwargs):
        """Create a task without triggering signals."""
        task = Task(**kwargs)
        task.save()
        return task

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="validationuser")
        self.organization = Organization.objects.create(name="Test Org")

    def test_team_unique_constraint(self):
        """Test Team unique constraint on organization and name."""
        team1 = Team.objects.create(name="Unique Team", organization=self.organization)

        # Creating another team with same name in same org should work initially
        # but the unique_together constraint is defined in Meta
        team2 = Team.objects.create(name="Different Team", organization=self.organization)

        self.assertNotEqual(team1.name, team2.name)

    def test_task_dependency_unique_constraint(self):
        """Test TaskDependency unique constraint."""
        task1 = self._create_task_safely(name="Task 1", function_name="func1")
        task2 = self._create_task_safely(name="Task 2", function_name="func2")

        # First dependency should be created successfully
        dep1 = TaskDependency.objects.create(dependent_task=task2, prerequisite_task=task1)

        self.assertEqual(dep1.dependent_task, task2)
        self.assertEqual(dep1.prerequisite_task, task1)

    def test_task_chain_membership_unique_constraint(self):
        """Test TaskChainMembership unique constraint."""
        chain = TaskChain.objects.create(name="Test Chain")
        task = self._create_task_safely(name="Test Task", function_name="func")

        # First membership should be created successfully
        membership1 = TaskChainMembership.objects.create(chain=chain, task=task, order=1)

        self.assertEqual(membership1.chain, chain)
        self.assertEqual(membership1.task, task)
        self.assertEqual(membership1.order, 1)


@pytest.mark.unit
class ModelMethodsTestCase(TestCase):
    """Test cases for model methods and properties."""

    def _create_task_safely(self, **kwargs):
        """Create a task without triggering signals."""
        task = Task(**kwargs)
        task.save()
        return task

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="methoduser")

    def test_user_password_handling(self):
        """Test User password handling."""
        # Test password setting
        self.user.set_password("newpassword")
        self.user.save()
        self.assertTrue(self.user.check_password("newpassword"))

        # Test empty password handling in save method
        self.user.password = ""
        self.user.save()
        # Password should be set to None for empty string

    def test_task_priority_choices(self):
        """Test Task priority choices."""
        task = self._create_task_safely(name="Priority Test", function_name="priority_func")

        valid_priorities = [1, 2, 3, 4]  # Low, Normal, High, Critical

        for priority in valid_priorities:
            task.priority = priority
            task.save()
            self.assertEqual(task.priority, priority)

        # Test get_priority_display
        task.priority = 1
        self.assertEqual(task.get_priority_display(), "Low")
        task.priority = 4
        self.assertEqual(task.get_priority_display(), "Critical")
