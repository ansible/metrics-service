"""
Development environment overrides
Inherits from ./defaults.py and adds dev-specific defaults
"""

from apps.settings.defaults import framework_validators

DEBUG = True
ALLOW_SHARED_RESOURCE_CUSTOM_ROLES = False

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://metrics-service:8000",
]
"""CSRF settings to allow origins to make requests, NOTE: Only use in development!"""

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
"""Cache settings - use dummy cache for development to avoid caching issues"""

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
"""Email backend for development (console output)"""

LOGGING__loggers__django__level = "DEBUG"
LOGGING__loggers__metrics_service__level = "DEBUG"
LOGGING__loggers__ansible_base__level = "DEBUG"
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
    # disable "Including URLS from ...", "Module ... does not specify urls.py"
    "ansible_base.lib.dynamic_config.dynamic_urls": {
        "level": "INFO",
    },
    # disable 8 lines of JWT per request
    "ansible_base.jwt_consumer.common.auth": {
        "level": "INFO",
    },
}

validators = [
    *framework_validators,  # Include framework-provided normalization validators
]
