"""
Tests for apps.core.management.commands.metrics_service module - init-service-id functionality.
"""

from io import StringIO

import pytest
from django.test import TestCase

from apps.core.management.commands.metrics_service import Command


@pytest.mark.django_db
class TestInitServiceIdCommand(TestCase):
    """Test the init_service_id management command."""

    def setUp(self):
        """Set up test fixtures."""
        self.command = Command()
        self.out = StringIO()
        self.err = StringIO()

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
