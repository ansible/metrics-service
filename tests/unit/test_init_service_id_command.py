"""
Tests for apps.core.management.commands.init_service_id module.
"""

import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.test import TestCase

from apps.core.management.commands.init_service_id import Command


@pytest.mark.django_db
class TestInitServiceIdCommand(TestCase):
    """Test the init_service_id management command."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.out = StringIO()
        self.err = StringIO()

    @patch("apps.core.management.commands.init_service_id.ServiceID")
    def test_handle_creates_service_id_when_none_exists(self, mock_service_id):
        """Test that command creates ServiceID when none exists."""
        # Mock ServiceID.objects.count() to return 0
        mock_service_id.objects.count.return_value = 0

        # Mock ServiceID creation
        mock_instance = MagicMock()
        mock_instance.pk = "test-service-id-123"
        mock_service_id.objects.create.return_value = mock_instance

        # Set command stdout to capture output
        self.command.stdout = self.out

        # Run the command
        self.command.handle()

        # Verify ServiceID was created
        mock_service_id.objects.create.assert_called_once()

        # Verify success message was written
        output = self.out.getvalue()
        assert "Created ServiceID: test-service-id-123" in output

    @patch("apps.core.management.commands.init_service_id.ServiceID")
    def test_handle_skips_creation_when_service_id_exists(self, mock_service_id):
        """Test that command skips creation when ServiceID already exists."""
        # Mock ServiceID.objects.count() to return 1
        mock_service_id.objects.count.return_value = 1

        # Mock existing ServiceID
        mock_instance = MagicMock()
        mock_instance.pk = "existing-service-id-456"
        mock_service_id.objects.first.return_value = mock_instance

        # Set command stdout to capture output
        self.command.stdout = self.out

        # Run the command
        self.command.handle()

        # Verify ServiceID was not created
        mock_service_id.objects.create.assert_not_called()

        # Verify warning message was written
        output = self.out.getvalue()
        assert "ServiceID exists: existing-service-id-456" in output

    @patch("apps.core.management.commands.init_service_id.ServiceID")
    def test_handle_multiple_service_ids_exist(self, mock_service_id):
        """Test command behavior when multiple ServiceIDs exist."""
        # Mock ServiceID.objects.count() to return 2
        mock_service_id.objects.count.return_value = 2

        # Mock existing ServiceID
        mock_instance = MagicMock()
        mock_instance.pk = "first-service-id-789"
        mock_service_id.objects.first.return_value = mock_instance

        # Set command stdout to capture output
        self.command.stdout = self.out

        # Run the command
        self.command.handle()

        # Verify ServiceID was not created
        mock_service_id.objects.create.assert_not_called()

        # Verify warning message was written
        output = self.out.getvalue()
        assert "ServiceID exists: first-service-id-789" in output

    def test_command_help_text(self):
        """Test that command has proper help text."""
        assert self.command.help == "Initialize ServiceID for ansible-base resource registry"

    @patch("apps.core.management.commands.init_service_id.ServiceID")
    def test_call_command_integration(self, mock_service_id):
        """Test calling the command via Django's call_command."""
        # Mock ServiceID.objects.count() to return 0
        mock_service_id.objects.count.return_value = 0

        # Mock ServiceID creation
        mock_instance = MagicMock()
        mock_instance.pk = "integration-test-id"
        mock_service_id.objects.create.return_value = mock_instance

        # Capture output
        out = StringIO()

        # Call the command
        call_command("init_service_id", stdout=out)

        # Verify ServiceID was created
        mock_service_id.objects.create.assert_called_once()

        # Verify output contains success message
        output = out.getvalue()
        assert "Created ServiceID: integration-test-id" in output

    @patch("apps.core.management.commands.init_service_id.ServiceID")
    def test_handle_with_args_and_options(self, mock_service_id):
        """Test that handle method accepts args and options parameters."""
        # Mock ServiceID.objects.count() to return 0
        mock_service_id.objects.count.return_value = 0

        # Mock ServiceID creation
        mock_instance = MagicMock()
        mock_instance.pk = "args-options-test"
        mock_service_id.objects.create.return_value = mock_instance

        # Set command stdout to capture output
        self.command.stdout = self.out

        # Call handle with args and options
        self.command.handle("arg1", "arg2", option1="value1")

        # Verify ServiceID was created (args/options should be ignored)
        mock_service_id.objects.create.assert_called_once()

        # Verify success message was written
        output = self.out.getvalue()
        assert "Created ServiceID: args-options-test" in output

    def test_import_service_id_model(self):
        """Test that ServiceID model can be imported correctly."""
        from ansible_base.resource_registry.models.service_identifier import ServiceID

        # Verify the import works and ServiceID is a class
        assert ServiceID is not None
        assert hasattr(ServiceID, "objects")

    def test_import_base_command(self):
        """Test that BaseCommand can be imported correctly."""
        from django.core.management.base import BaseCommand

        # Verify the import works
        assert BaseCommand is not None
        assert hasattr(BaseCommand, "handle")

    def test_command_inherits_from_base_command(self):
        """Test that Command class properly inherits from BaseCommand."""
        from django.core.management.base import BaseCommand

        assert issubclass(Command, BaseCommand)
        assert hasattr(self.command, "handle")
        assert hasattr(self.command, "help")

