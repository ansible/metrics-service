"""
Integration tests for production environment variable validators.

These tests verify that validators enforce requirements when running in production mode.
They use subprocess.run to actually boot Django and verify it crashes with clear errors
when required production environment variables are missing.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


def get_minimal_production_env():
    """Return minimal production environment with all required variables set.

    This helper provides a complete production environment that passes validation.
    Individual tests can delete specific variables to test validator enforcement.
    """
    env = os.environ.copy()
    env.update(
        {
            "METRICS_SERVICE_MODE": "production",
            "DJANGO_SETTINGS_MODULE": "metrics_service.settings",
            "METRICS_SERVICE_SECRET_KEY": "test-secret-key",
            "METRICS_SERVICE_RESOURCE_SERVER__URL": "http://gateway",
            "METRICS_SERVICE_RESOURCE_SERVER__SECRET_KEY": "resource-secret",
            "METRICS_SERVICE_ANSIBLE_BASE_JWT_KEY": "jwt-key",
            "METRICS_SERVICE_DATABASES__default__HOST": "localhost",
            "METRICS_SERVICE_DATABASES__default__USER": "user",
            "METRICS_SERVICE_DATABASES__default__PASSWORD": "pass",
            "METRICS_SERVICE_DATABASES__awx__HOST": "localhost",
            "METRICS_SERVICE_DATABASES__awx__USER": "user",
            "METRICS_SERVICE_DATABASES__awx__PASSWORD": "pass",
            "METRICS_SERVICE_SEGMENT_WRITE_KEY": "segment-key",
            "METRICS_SERVICE_ALLOWED_HOSTS": '["example.com"]',
        }
    )
    return env


class TestProductionValidatorEnforcement:
    """Test that production validators actually fail when requirements aren't met.

    These integration tests use subprocess.run to boot Django in production mode
    and verify it refuses to start when required environment variables are missing.
    This proves the validators work in real server startup scenarios, not just mocks.
    """

    @pytest.mark.parametrize(
        "omitted_var,expected_in_error",
        [
            ("METRICS_SERVICE_ALLOWED_HOSTS", "ALLOWED_HOSTS"),
            ("METRICS_SERVICE_SEGMENT_WRITE_KEY", "SEGMENT_WRITE_KEY"),
            ("METRICS_SERVICE_ANSIBLE_BASE_JWT_KEY", "ANSIBLE_BASE_JWT_KEY"),
            ("METRICS_SERVICE_RESOURCE_SERVER__SECRET_KEY", "RESOURCE_SERVER__SECRET_KEY"),
        ],
    )
    def test_production_mode_requires_variable(self, omitted_var, expected_in_error):
        """Test that Django crashes at startup when a required production variable is missing.

        This parametrized test exercises each of the four newly uncommented validators
        to ensure they prevent misconfigured production deployments.
        """
        env = get_minimal_production_env()

        # Remove the specific variable being tested
        del env[omitted_var]

        result = subprocess.run(
            [sys.executable, "manage.py", "check"],
            env=env,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        # Django should fail to boot
        assert result.returncode != 0, f"Production mode should crash without {omitted_var}"

        # Error message should clearly identify the missing variable
        output = result.stderr + result.stdout
        assert expected_in_error in output, (
            f"Error should mention {expected_in_error} when {omitted_var} is missing. Got: {output}"
        )
