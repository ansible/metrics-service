"""
Test settings for metrics_service.

This module provides test-specific Django settings that override
the default settings for running tests with pytest.

Tests use PostgreSQL to match the production environment setup.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Basic required settings
SECRET_KEY = "test-secret-key-for-testing-only-not-secure"
DEBUG = False
TESTING = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Application definition - simplified for testing
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
]

# DAB apps - matching production configuration
DAB_APPS = [
    "ansible_base",
    "ansible_base.rest_filters",
    "ansible_base.rest_pagination",
    "ansible_base.rbac",
    "ansible_base.activitystream",
    "ansible_base.jwt_consumer",
    "ansible_base.resource_registry",
]

LOCAL_APPS = [
    "apps.core",
    "apps.dynamic_settings",
    "apps.tasks",
    "apps.dashboard",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + DAB_APPS + LOCAL_APPS

# Django ansible-base settings for testing
ANSIBLE_BASE_ORGANIZATION_MODEL = "core.Organization"
ANSIBLE_BASE_TEAM_MODEL = "core.Team"
ANSIBLE_BASE_USER_MODEL = "core.User"
AUTH_USER_MODEL = "core.User"

# RBAC settings - register models for permission tracking
ANSIBLE_BASE_RBAC_MODEL_REGISTRY = {
    "core.Organization": {"parent_field_name": None},
    "core.Team": {"parent_field_name": "organization"},
    "core.User": {"parent_field_name": None},
}

# Default RBAC roles - created automatically on migrate
ANSIBLE_BASE_MANAGED_ROLE_REGISTRY = {
    "sys_auditor": {"name": "Platform Auditor"},  # View-only, system-wide
    "org_admin": {},  # Organization Admin - all perms on org + children
    "org_member": {},  # Organization Member - member perm on org
    "team_admin": {},  # Team Admin - all perms on team
    "team_member": {},  # Team Member - member perm on team
}

ANSIBLE_BASE_BYPASS_SUPERUSER_FLAGS = ["is_superuser"]
ANSIBLE_BASE_BYPASS_ACTION_FLAGS = {
    "create": "is_superuser",
    "read": "is_superuser",
    "update": "is_superuser",
    "delete": "is_superuser",
}
ANSIBLE_BASE_ALLOW_SINGLETON_USER_ROLES = True
ANSIBLE_BASE_ALLOW_SINGLETON_TEAM_ROLES = True

# Additional DAB RBAC settings required for tests
ANSIBLE_BASE_CHECK_RELATED_PERMISSIONS = ["use", "change", "view"]
ANSIBLE_BASE_CACHE_PARENT_PERMISSIONS = False
ANSIBLE_BASE_EVALUATIONS_IGNORE_CONFLICTS = False
ANSIBLE_BASE_DELETE_REQUIRE_CHANGE = False
ANSIBLE_BASE_CREATOR_DEFAULTS = ["add", "change", "delete", "view"]

# Configure which roles can be synced via JWT from gateway
ANSIBLE_BASE_JWT_MANAGED_ROLES = [
    "Platform Auditor",
    "Organization Admin",
    "Organization Member",
    "Team Admin",
    "Team Member",
]

# Service identification
SERVICE_TYPE = "metrics-service"
SERVICE_ID = "test-service-id"

# Login/Logout URLs for DRF browsable API
LOGIN_URL = "/api-auth/login/"
LOGOUT_URL = "/api-auth/logout/"

# Middleware - ServicePrefix at start, APIRootView at end
MIDDLEWARE = [
    "apps.core.middleware.ServicePrefixMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.APIRootViewMiddleware",
]

# URLs - simplified for testing to avoid oauth2 provider conflicts
ROOT_URLCONF = "metrics_service.test_urls"

# Templates
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Use PostgreSQL for tests to match production environment
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("METRICS_SERVICE_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("METRICS_SERVICE_DB_PORT", "5432"),
        "USER": os.environ.get("METRICS_SERVICE_DB_USER", "metrics_service"),
        "PASSWORD": os.environ.get("METRICS_SERVICE_DB_PASSWORD", "metrics_service"),
        "NAME": os.environ.get("METRICS_SERVICE_TEST_DB_NAME", "metrics_service"),
        "OPTIONS": {
            "sslmode": os.environ.get("METRICS_SERVICE_DB_SSLMODE", "prefer"),
        },
        "TEST": {
            # Let Django create unique test database names automatically
            "NAME": None,
        },
    }
}


# Enable migrations during tests for proper schema management with PostgreSQL
# This ensures tests run with the same schema as production

# Security settings for testing
SECRET_KEY = "test-secret-key-for-testing-only-not-secure"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Disable caching during tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Use faster password hashing for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Email settings for testing
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Disable logging during tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "root": {
        "handlers": ["null"],
    },
}

# Disable dispatcherd during tests to avoid background processes
DISPATCHERD_ENABLED = False
DEVELOPER_MODE_ENABLED = True

# Disable feature enables during tests
FEATURE_ENABLED = {
    "ANONYMIZED_DATA_COLLECTION": False,
    "METRICS_COLLECTION_ENABLED": False,
}

# Test-specific apps - INSTALLED_APPS is already defined in defaults.py

# Static files settings for tests
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Media files settings for tests
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# REST Framework settings for tests
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# Test database settings
TEST_DATABASE_PREFIX = "test_"
