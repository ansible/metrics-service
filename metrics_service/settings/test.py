"""
Test-specific settings for metrics_service.
"""

import os

# Import all settings from defaults first
from .defaults import *  # noqa: F403, F401
from .defaults import FEATURE_FLAGS, LOGGING, REST_FRAMEWORK  # noqa: F401

# Disable debug for tests
DEBUG = False

# Use PostgreSQL with test database for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("METRICS_SERVICE_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("METRICS_SERVICE_DB_PORT", "55433"),
        "USER": os.environ.get("METRICS_SERVICE_DB_USER", "metrics_service"),
        "PASSWORD": os.environ.get("METRICS_SERVICE_DB_PASSWORD", "metrics_service"),
        "NAME": os.environ.get("METRICS_SERVICE_TEST_DB_NAME", "test_metrics_service"),
        "OPTIONS": {
            "sslmode": os.environ.get("METRICS_SERVICE_DB_SSLMODE", "prefer"),
        },
        "TEST": {
            "NAME": os.environ.get("METRICS_SERVICE_TEST_DB_NAME", "test_metrics_service"),
        },
    }
}

# Use in-memory cache for tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Password hashers for tests (faster)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Session configuration for tests
SESSION_ENGINE = "django.contrib.sessions.backends.db"


# For faster tests, we could disable migrations for specific apps
# but keep Django core migrations enabled
# MIGRATION_MODULES = {
#     'core': None,
#     'api': None,
#     'health': None,
# }

# Logging configuration for tests (minimal)
LOGGING["loggers"]["metrics_service"]["level"] = "WARNING"
LOGGING["loggers"]["ansible_base"]["level"] = "WARNING"
LOGGING["loggers"]["django"]["level"] = "WARNING"
LOGGING["loggers"][""]["level"] = "ERROR"

# Disable feature flags for tests unless explicitly enabled
FEATURE_FLAGS.update(
    {
        "DISPATCHERD_ENABLED": False,
    }
)

# Static files for tests
STATIC_ROOT = "/static"
MEDIA_ROOT = "/media"

# Security settings for tests
SECRET_KEY = "test-secret-key"
ALLOWED_HOSTS = ["*"]

# Disable CSRF for API tests
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "rest_framework.authentication.SessionAuthentication",
]

# Include required DAB apps for testing
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "oauth2_provider",
    "ansible_base.activitystream",
    "ansible_base.rbac",
    "ansible_base.resource_registry",
    "ansible_base.authentication",
    "apps.core",
    "apps.api",
    "apps.health",
]

# Test-specific feature flags
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# Additional DAB settings for tests
ANSIBLE_BASE_MANAGED_ROLE_REGISTRY = {}

# Additional OAuth2 settings for tests
OAUTH2_PROVIDER_ID_TOKEN_MODEL = "oauth2_provider.IDToken"

# ANSIBLE_BASE settings for tests
ANSIBLE_BASE_BYPASS_SUPERUSER_FLAGS = ["is_superuser"]
ANSIBLE_BASE_BYPASS_ACTION_FLAGS = {
    "create": "is_superuser",
    "read": "is_superuser",
    "update": "is_superuser",
    "delete": "is_superuser",
}

# Disable RBAC for tests since models aren't registered
ANSIBLE_BASE_RBAC_ENABLED = False

# Override permissions for tests
ANSIBLE_BASE_ALLOW_SINGLETON_USER_WITHOUT_DAB_RBAC = True
