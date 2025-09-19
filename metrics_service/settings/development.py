"""
Development settings for metrics_service.
These settings are optimized for local development with Docker.
"""

from .defaults import *  # noqa: F403, F401

# Override DEBUG setting
DEBUG = True

# More permissive ALLOWED_HOSTS for development
ALLOWED_HOSTS = ["*"]

# Development-specific logging with more verbose output
LOGGING["loggers"]["django"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["metrics_service"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["ansible_base"]["level"] = "DEBUG"  # noqa: F405

# Disable CSRF for easier API testing in development
# Note: Only use in development!
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://metrics-service:8000",
]

# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Cache settings - use dummy cache for development to avoid caching issues
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Email backend for development (console output)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Development-specific feature flags
DISPATCHERD_ENABLED = True

# Static files serving in development
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
