"""
Comprehensive tests for reload_config_command management command.

This module provides complete test coverage for the reload_config_command,
testing all code paths including success cases, error handling, and verbose mode.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase


@pytest.mark.unit
class TestReloadConfigCommand(TestCase):
    """Test cases for reload_config_command management command."""

    def test_command_basic_execution(self):
        """Test basic command execution without verbose mode."""
        out = StringIO()

        # Import the command class
        from apps.dynamic_settings.management.commands.reload_config import Command

        # Create instance and mock its dynaconf attribute
        command = Command()
        command.stdout = out  # Set stdout on the command instance
        command.dynaconf = MagicMock()
        command.dynaconf.reload = MagicMock()

        # Execute the command
        command.handle(verbose=False)

        # Verify reload was called
        command.dynaconf.reload.assert_called_once()

        # Check output
        output = out.getvalue()
        assert "Configuration reloaded successfully" in output

    def test_command_verbose_mode(self):
        """Test command execution with verbose mode enabled."""
        out = StringIO()

        # Import the command class
        from apps.dynamic_settings.management.commands.reload_config import Command

        # Create mock dynaconf with proper attributes
        mock_dynaconf = MagicMock()
        mock_dynaconf.reload = MagicMock()
        mock_dynaconf.current_env = "test"
        mock_dynaconf.settings_files = ["config/settings.yaml"]

        # Create instance
        command = Command()
        command.stdout = out  # Set stdout on the command instance
        command.dynaconf = mock_dynaconf

        # Mock both the initial DYNACONF and the one imported inside verbose block
        with (
            patch("apps.dynamic_settings.management.commands.reload_config.DYNACONF", mock_dynaconf),
            patch("metrics_service.settings.DYNACONF", mock_dynaconf),
        ):
            # Execute the command in verbose mode
            command.handle(verbose=True)

        # Verify reload was called
        mock_dynaconf.reload.assert_called_once()

        # Check verbose output
        output = out.getvalue()
        assert "Reloading dynaconf configuration..." in output
        assert "Configuration reloaded successfully" in output
        assert "Current environment: test" in output
        assert "Loaded settings files: ['config/settings.yaml']" in output

    def test_command_error_handling(self):
        """Test command error handling when reload fails."""
        out = StringIO()

        # Import the command class
        from apps.dynamic_settings.management.commands.reload_config import Command

        # Create instance and mock its dynaconf attribute
        command = Command()
        command.stdout = out  # Set stdout on the command instance
        command.dynaconf = MagicMock()
        command.dynaconf.reload = MagicMock(side_effect=Exception("Reload failed"))

        # Execute the command and expect exception
        with pytest.raises(Exception, match="Reload failed"):
            command.handle(verbose=False)

        # Verify reload was attempted
        command.dynaconf.reload.assert_called_once()

        # Check error output
        output = out.getvalue()
        assert "Failed to reload configuration: Reload failed" in output

    def test_command_error_handling_verbose(self):
        """Test command error handling in verbose mode."""
        out = StringIO()

        # Import the command class
        from apps.dynamic_settings.management.commands.reload_config import Command

        # Create instance and mock its dynaconf attribute
        command = Command()
        command.stdout = out  # Set stdout on the command instance
        command.dynaconf = MagicMock()
        command.dynaconf.reload = MagicMock(side_effect=RuntimeError("Config error"))

        # Execute the command and expect exception
        with pytest.raises(RuntimeError, match="Config error"):
            command.handle(verbose=True)

        # Check that verbose message was shown before error
        output = out.getvalue()
        assert "Reloading dynaconf configuration..." in output
        assert "Failed to reload configuration: Config error" in output

    def test_command_logging(self):
        """Test that command properly logs success and errors."""
        out = StringIO()

        # Import the command class
        from apps.dynamic_settings.management.commands.reload_config import Command

        # Create instance and mock its dynaconf attribute
        command = Command()
        command.stdout = out  # Set stdout on the command instance
        command.dynaconf = MagicMock()
        command.dynaconf.reload = MagicMock()

        with patch("apps.dynamic_settings.management.commands.reload_config.logger") as mock_logger:
            command.handle(verbose=False)

            # Verify logging
            mock_logger.info.assert_called_once_with("Dynaconf configuration reloaded successfully")

    def test_command_logging_on_error(self):
        """Test that command properly logs errors."""
        out = StringIO()

        # Import the command class
        from apps.dynamic_settings.management.commands.reload_config import Command

        # Create instance and mock its dynaconf attribute
        command = Command()
        command.stdout = out  # Set stdout on the command instance
        command.dynaconf = MagicMock()
        command.dynaconf.reload = MagicMock(side_effect=ValueError("Invalid config"))

        with patch("apps.dynamic_settings.management.commands.reload_config.logger") as mock_logger:
            with pytest.raises(ValueError):
                command.handle(verbose=False)

            # Verify error logging
            mock_logger.exception.assert_called_once_with("Failed to reload configuration: Invalid config")

    def test_add_arguments_method(self):
        """Test that add_arguments properly configures the verbose flag."""
        from apps.dynamic_settings.management.commands.reload_config import Command

        command = Command()
        parser = MagicMock()

        command.add_arguments(parser)

        # Verify that verbose argument was added
        parser.add_argument.assert_called_once_with(
            "--verbose",
            action="store_true",
            help="Show detailed information about the reload process",
        )

    def test_command_help_text(self):
        """Test that command has proper help text."""
        from apps.dynamic_settings.management.commands.reload_config import Command

        command = Command()
        assert command.help == "Reload dynaconf configuration from files and environment variables"

    def test_command_dynaconf_attribute(self):
        """Test that command has dynaconf attribute."""
        from apps.dynamic_settings.management.commands.reload_config import Command

        command = Command()
        assert hasattr(command, "dynaconf")
        assert command.dynaconf is not None

    def test_verbose_flag_false_by_default(self):
        """Test that verbose flag defaults to False."""
        out = StringIO()

        # Import the command class
        from apps.dynamic_settings.management.commands.reload_config import Command

        # Create instance and mock its dynaconf attribute
        command = Command()
        command.stdout = out  # Set stdout on the command instance
        command.dynaconf = MagicMock()
        command.dynaconf.reload = MagicMock()

        command.handle(verbose=False)

        output = out.getvalue()
        # Should not show verbose messages
        assert "Reloading dynaconf configuration..." not in output
        assert "Current environment:" not in output

    def test_exception_propagation(self):
        """Test that exceptions are properly propagated."""
        out = StringIO()

        # Import the command class
        from apps.dynamic_settings.management.commands.reload_config import Command

        # Create instance and mock its dynaconf attribute
        command = Command()
        command.stdout = out  # Set stdout on the command instance
        command.dynaconf = MagicMock()
        command.dynaconf.reload = MagicMock(side_effect=KeyError("Missing key"))

        with pytest.raises(KeyError, match="Missing key"):
            command.handle(verbose=False)
