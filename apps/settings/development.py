"""
Development environment overrides
Inherits from ./defaults.py and adds dev-specific defaults
"""

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

ALLOW_SHARED_RESOURCE_CUSTOM_ROLES = False

SECRET_KEY = "dev-secret-key-change-in-production"

# Cache settings - use dummy cache for development to avoid caching issues
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# CSRF settings to allow origins to make requests, NOTE: Only use in development!
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://metrics-service:8000",
]

DEBUG = True

# Email backend for development (console output)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

LOGGING__loggers__ansible_base__level = "DEBUG"
LOGGING__loggers__django__level = "DEBUG"
LOGGING__loggers__metrics_service__level = "DEBUG"
LOGGING__loggers = {
    "dynaconf_merge": True,
    # disable autoreload DEBUG - lists all watched files
    "django.utils.autoreload": {
        "level": "INFO",
    },
    # disable db DEBUG - shows sql for all queries
    "django.db.backends": {
        "level": "INFO",
    },
    # disable template DEBUG - filters out debug toolbar VariableDoesNotExist exceptions
    "django.template": {
        "level": "INFO",
    },
}
