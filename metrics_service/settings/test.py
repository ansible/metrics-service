"""
Test-specific settings for metrics_service.
"""

from .defaults import *  # noqa: F401,F403

# Disable debug for tests
DEBUG = False

# Use in-memory database for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
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


# Disable migrations for tests
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

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
STATIC_ROOT = "/tmp/static"
MEDIA_ROOT = "/tmp/media"

# Security settings for tests
SECRET_KEY = "test-secret-key"
ALLOWED_HOSTS = ["*"]

# Disable CSRF for API tests
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "rest_framework.authentication.SessionAuthentication",
]

# Test-specific feature flags
TEST_RUNNER = "django.test.runner.DiscoverRunner"
