"""
Unit tests for ServiceConfig service.
"""

import pytest
from django.test import TestCase

from apps.tasks.services.service_config import ServiceConfig


@pytest.mark.unit
class ServiceConfigTestCase(TestCase):
    """Test cases for ServiceConfig service."""

    def test_initialization_with_defaults(self):
        """Test ServiceConfig initialization with default values."""
        config = ServiceConfig({})

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, "8000")
        self.assertEqual(config.workers, 4)
        self.assertEqual(config.timeout, 3600)
        self.assertEqual(config.max_tasks, 100)
        self.assertEqual(config.log_level, "INFO")

    def test_initialization_with_custom_values(self):
        """Test ServiceConfig initialization with custom values."""
        options = {
            "host": "localhost",
            "port": "9000",
            "workers": 8,
            "timeout": 7200,
            "max_tasks": 200,
            "log_level": "DEBUG",
        }
        config = ServiceConfig(options)

        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.port, "9000")
        self.assertEqual(config.workers, 8)
        self.assertEqual(config.timeout, 7200)
        self.assertEqual(config.max_tasks, 200)
        self.assertEqual(config.log_level, "DEBUG")

    def test_initialization_with_partial_values(self):
        """Test ServiceConfig initialization with partial custom values."""
        options = {"host": "localhost", "workers": 6, "log_level": "WARNING"}
        config = ServiceConfig(options)

        # Custom values
        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.workers, 6)
        self.assertEqual(config.log_level, "WARNING")

        # Default values
        self.assertEqual(config.port, "8000")
        self.assertEqual(config.timeout, 3600)
        self.assertEqual(config.max_tasks, 100)

    def test_host_validation_valid(self):
        """Test valid host validation."""
        valid_hosts = ["127.0.0.1", "localhost", "localhost", "example.com", "my-server"]

        for host in valid_hosts:
            config = ServiceConfig({"host": host})
            self.assertEqual(config.host, host)

    def test_host_validation_invalid(self):
        """Test invalid host validation."""
        invalid_hosts = ["", None, 123, [], {}]

        for host in invalid_hosts:
            with self.assertRaises(ValueError) as cm:
                ServiceConfig({"host": host})
            self.assertIn("Invalid host", str(cm.exception))

    def test_port_validation_valid(self):
        """Test valid port validation."""
        valid_ports = ["8000", "9000", "80", "443", "65535", 8000, 9000]

        for port in valid_ports:
            config = ServiceConfig({"port": port})
            self.assertEqual(config.port, port)

    def test_workers_validation_valid(self):
        """Test valid workers validation."""
        valid_workers = [1, 2, 4, 8, 16, 32]

        for workers in valid_workers:
            config = ServiceConfig({"workers": workers})
            self.assertEqual(config.workers, workers)

    def test_workers_validation_invalid(self):
        """Test invalid workers validation."""
        invalid_workers = [0, -1, -5, "4", None, [], {}, 0.5]

        for workers in invalid_workers:
            with self.assertRaises(ValueError) as cm:
                ServiceConfig({"workers": workers})
            self.assertIn("Invalid workers count", str(cm.exception))

    def test_timeout_validation_valid(self):
        """Test valid timeout validation."""
        valid_timeouts = [1, 60, 3600, 7200, 86400]

        for timeout in valid_timeouts:
            config = ServiceConfig({"timeout": timeout})
            self.assertEqual(config.timeout, timeout)

    def test_timeout_validation_invalid(self):
        """Test invalid timeout validation."""
        invalid_timeouts = [0, -1, -3600, "3600", None, [], {}, 0.5]

        for timeout in invalid_timeouts:
            with self.assertRaises(ValueError) as cm:
                ServiceConfig({"timeout": timeout})
            self.assertIn("Invalid timeout", str(cm.exception))

    def test_max_tasks_validation_valid(self):
        """Test valid max_tasks validation."""
        valid_max_tasks = [1, 10, 100, 500, 1000]

        for max_tasks in valid_max_tasks:
            config = ServiceConfig({"max_tasks": max_tasks})
            self.assertEqual(config.max_tasks, max_tasks)

    def test_max_tasks_validation_invalid(self):
        """Test invalid max_tasks validation."""
        invalid_max_tasks = [0, -1, -100, "100", None, [], {}, 0.5]

        for max_tasks in invalid_max_tasks:
            with self.assertRaises(ValueError) as cm:
                ServiceConfig({"max_tasks": max_tasks})
            self.assertIn("Invalid max_tasks", str(cm.exception))

    def test_log_level_validation_valid(self):
        """Test valid log_level validation."""
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]

        for log_level in valid_log_levels:
            config = ServiceConfig({"log_level": log_level})
            self.assertEqual(config.log_level, log_level)

    def test_log_level_validation_invalid(self):
        """Test invalid log_level validation."""
        invalid_log_levels = ["TRACE", "CRITICAL", "debug", "info", "", None, 123, []]

        for log_level in invalid_log_levels:
            with self.assertRaises(ValueError) as cm:
                ServiceConfig({"log_level": log_level})
            self.assertIn("Invalid log_level", str(cm.exception))

    def test_to_dict(self):
        """Test to_dict method."""
        options = {
            "host": "localhost",
            "port": "9000",
            "workers": 8,
            "timeout": 7200,
            "max_tasks": 200,
            "log_level": "DEBUG",
        }
        config = ServiceConfig(options)
        result = config.to_dict()

        expected = {
            "host": "localhost",
            "port": "9000",
            "workers": 8,
            "timeout": 7200,
            "max_tasks": 200,
            "log_level": "DEBUG",
        }

        self.assertEqual(result, expected)

    def test_to_dict_with_defaults(self):
        """Test to_dict method with default values."""
        config = ServiceConfig({})
        result = config.to_dict()

        expected = {
            "host": "127.0.0.1",
            "port": "8000",
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        self.assertEqual(result, expected)

    def test_string_representation(self):
        """Test string representation of ServiceConfig."""
        config = ServiceConfig({"host": "localhost", "port": "9000", "workers": 6, "log_level": "DEBUG"})

        result = str(config)
        expected = "ServiceConfig(host=localhost, port=9000, workers=6, log_level=DEBUG)"

        self.assertEqual(result, expected)

    def test_string_representation_defaults(self):
        """Test string representation with defaults."""
        config = ServiceConfig({})

        result = str(config)
        expected = "ServiceConfig(host=127.0.0.1, port=8000, workers=4, log_level=INFO)"

        self.assertEqual(result, expected)

    def test_defaults_constant(self):
        """Test that DEFAULTS constant has correct values."""
        expected_defaults = {
            "host": "127.0.0.1",
            "port": "8000",
            "workers": 4,
            "timeout": 3600,
            "max_tasks": 100,
            "log_level": "INFO",
        }

        self.assertEqual(ServiceConfig.DEFAULTS, expected_defaults)

    def test_valid_log_levels_constant(self):
        """Test that VALID_LOG_LEVELS constant has correct values."""
        expected_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]

        self.assertEqual(ServiceConfig.VALID_LOG_LEVELS, expected_log_levels)

    def test_edge_case_numeric_string_port(self):
        """Test numeric string port handling."""
        config = ServiceConfig({"port": "8080"})
        self.assertEqual(config.port, "8080")

    def test_edge_case_large_valid_values(self):
        """Test large but valid configuration values."""
        options = {"workers": 64, "timeout": 86400, "max_tasks": 10000}  # 24 hours
        config = ServiceConfig(options)

        self.assertEqual(config.workers, 64)
        self.assertEqual(config.timeout, 86400)
        self.assertEqual(config.max_tasks, 10000)

    def test_multiple_validation_errors(self):
        """Test that first validation error is raised."""
        # Test with multiple invalid values - should raise first error encountered
        with self.assertRaises(ValueError) as cm:
            ServiceConfig({"host": "", "workers": 0, "log_level": "INVALID"})  # Invalid  # Also invalid  # Also invalid

        # Should get the first validation error (host)
        self.assertIn("Invalid host", str(cm.exception))
