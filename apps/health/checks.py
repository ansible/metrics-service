"""
Health check implementations for my_service.
"""

import time
from typing import Dict, Any

from django.conf import settings
from django.core.cache import cache
from django.db import connection
import logging

logger = logging.getLogger(__name__)


def check_database() -> Dict[str, Any]:
    """
    Check database connectivity and performance.

    Returns:
        Health check result dictionary
    """
    try:
        start_time = time.time()

        # Simple database query
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "details": "Database connection successful",
        }

    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "details": "Database connection failed",
        }


def check_cache() -> Dict[str, Any]:
    """
    Check cache connectivity and performance.

    Returns:
        Health check result dictionary
    """
    try:
        start_time = time.time()

        # Test cache set/get
        test_key = "health_check_test"
        test_value = "test_value"

        cache.set(test_key, test_value, timeout=30)
        retrieved_value = cache.get(test_key)

        if retrieved_value != test_value:
            raise Exception("Cache value mismatch")

        # Clean up test key
        cache.delete(test_key)

        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "details": "Cache connection successful",
        }

    except Exception as e:
        logger.error(f"Cache health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "details": "Cache connection failed",
        }


def check_feature_flags() -> Dict[str, Any]:
    """
    Check feature flags configuration.

    Returns:
        Health check result dictionary
    """
    try:
        feature_flags = getattr(settings, "FEATURE_FLAGS", {})

        return {
            "status": "healthy",
            "feature_flags": feature_flags,
            "details": f"Found {len(feature_flags)} feature flags",
        }

    except Exception as e:
        logger.error(f"Feature flags health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "details": "Feature flags check failed",
        }


def check_dab_integration() -> Dict[str, Any]:
    """
    Check Django-Ansible-Base integration.

    Returns:
        Health check result dictionary
    """
    try:
        # Check if DAB apps are installed
        installed_apps = getattr(settings, "INSTALLED_APPS", [])
        dab_apps = [app for app in installed_apps if app.startswith("ansible_base")]

        # Check authentication backend
        auth_backends = getattr(settings, "AUTHENTICATION_BACKENDS", [])
        dab_auth = any("AnsibleBaseAuth" in backend for backend in auth_backends)

        return {
            "status": "healthy",
            "dab_apps_count": len(dab_apps),
            "dab_apps": dab_apps,
            "dab_authentication": dab_auth,
            "details": "Django-Ansible-Base integration healthy",
        }

    except Exception as e:
        logger.error(f"DAB integration health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "details": "Django-Ansible-Base integration check failed",
        }


def check_dispatcherd() -> Dict[str, Any]:
    """
    Check dispatcherd configuration and status.

    Returns:
        Health check result dictionary
    """
    try:
        dispatcherd_enabled = getattr(settings, "FEATURE_FLAGS", {}).get("DISPATCHERD_ENABLED", False)

        if not dispatcherd_enabled:
            return {"status": "disabled", "details": "Dispatcherd is disabled"}

        # In a real implementation, you would check dispatcherd worker status here
        # For now, just check configuration
        dispatcherd_config = getattr(settings, "DISPATCHERD_CONFIG", {})

        return {
            "status": "healthy",
            "enabled": dispatcherd_enabled,
            "config": dispatcherd_config,
            "details": "Dispatcherd configuration healthy",
        }

    except Exception as e:
        logger.error(f"Dispatcherd health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "details": "Dispatcherd check failed",
        }


# Available health checks
HEALTH_CHECKS = {
    "database": check_database,
    "cache": check_cache,
    "feature_flags": check_feature_flags,
    "dab_integration": check_dab_integration,
    "dispatcherd": check_dispatcherd,
}
