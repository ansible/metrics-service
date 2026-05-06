"""
Top level settings file for all apps.

The settings here overrides any setting previously loaded
from the `metrics_service.settings`.
"""

import copy
import logging

from dynaconf import Dynaconf, Validator, post_hook

logger = logging.getLogger(__name__)

# Extra applications added after PSF templating
extra_applications = [
    "django_prometheus",
    "django_extensions",
]

# Default DAB applications layd out from PSF, add/remove according to the project needs,
# adjust `pyproject` dab extra dependencies acording to apps added/removed here
dab_applications = [
    "ansible_base.feature_flags",  # Must be first to ensure table exists before other apps' post_migrate signals
    "ansible_base.activitystream",
    "ansible_base.api_documentation",
    "ansible_base.jwt_consumer",
    "ansible_base.rbac",
    "ansible_base.resource_registry",
    "ansible_base.rest_filters",
    "ansible_base.rest_pagination",
]

# List of applications from the apps/ folder
project_applications = [
    "apps.core",
    "apps.dynamic_settings",
    "apps.tasks",
    "apps.dashboard",
    "apps.dashboard_reports",  # Dashboard data for automation-reports integration
]

# Final state of the INSTALLED_APPS that will merge with the rest of the settings
INSTALLED_APPS = [
    "dynaconf_merge_unique",  # DO NOT REMOVE THIS
    *dab_applications,
    *project_applications,
    *extra_applications,
    "django_generate_series",  # Dashboard data for automation-reports integration
]

# Enable debug mode
DEBUG = False

# REST framework settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "apps.core.renderers.ServiceBrowsableAPIRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
}

# Title of Swagger the API documentation
SPECTACULAR_SETTINGS__TITLE = "metrics_service API"
# Description of Swagger the API documentation
SPECTACULAR_SETTINGS__DESCRIPTION = "API documentation for the metrics_service"
# Version of Swagger the API documentation
SPECTACULAR_SETTINGS__VERSION = "v1"
# Split components into request and response for generating clients
SPECTACULAR_SETTINGS__COMPONENT_SPLIT_REQUEST = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "default",
    },
}
CSRF_TRUSTED_ORIGINS = []

# Databases settings, using PostgreSQL by default
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "",  # require to be set at runtime
        "PORT": "5432",
        "USER": "metrics_service",
        "PASSWORD": "",  # require to be set at runtime
        "NAME": "metrics_service",
        "OPTIONS": {
            "sslmode": "prefer",
        },
    },
    # AWX database for metrics-utility collector integration
    # Override with METRICS_SERVICE_DATABASES__awx__HOST, etc.
    "awx": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "",  # require to be set at runtime
        "PORT": "5432",
        "USER": "myuser",
        "PASSWORD": "",  # require to be set at runtime
        "NAME": "awx",
        "OPTIONS": {
            "sslmode": "prefer",
        },
    },
}

# Feature flag defaults
# only used by `metrics_service init-default-settings` (and `... run`)
# and only used when not already changed in the settings DB table
# also used by tasks - unless set in the db.
FEATURE_ENABLED = {
    # Local hourly/daily collectors, rollup, cleanup_metrics_data — see METRICS_COLLECTION_GROUP.
    "METRICS_COLLECTION": True,
    # Anonymization and Segment transmission only — does not gate METRICS_COLLECTION_GROUP.
    "ANONYMIZED_DATA_COLLECTION": True,
    # DASHBOARD_COLLECTION is intentionally omitted: set via METRICS_SERVICE_FEATURE_ENABLED__DASHBOARD_COLLECTION,
    # FEATURE_DASHBOARD_COLLECTION_ENABLED (top-level, installer convention), DAB AAPFlag
    # FEATURE_DASHBOARD_COLLECTION_ENABLED, or dynamic_settings.Setting — see get_feature_enabled_from_db.
}

# Used when generating API URLs in views, example "/api/metrics/"; None means "/api/"
URL_PREFIX = None


@post_hook
def load_prometheus_middlewares(settings: Dynaconf) -> dict:
    """Defer to execute after all settings are loaded."""
    middleware = settings.get("MIDDLEWARE", [])
    if "django_prometheus" in " ".join(middleware):
        return {}
    new = [
        "django_prometheus.middleware.PrometheusBeforeMiddleware",
        *middleware,
        "django_prometheus.middleware.PrometheusAfterMiddleware",
    ]
    return {"MIDDLEWARE": new}


# PostgreSQL session parameters supported for environment variable normalization
# Only the most commonly needed parameters are included to keep the feature focused
# For other parameters, use the standard OPTIONS['options'] = "-c param=value" syntax
SUPPORTED_PG_SESSION_PARAMS = {
    "datestyle",  # Date/time display format (e.g., "iso, mdy")
    "search_path",  # Schema search order (e.g., "public,myschema")
    "timezone",  # Session timezone (e.g., "UTC", "America/New_York")
    "application_name",  # Identifier shown in pg_stat_activity
}


def _normalize_postgresql_options(databases):
    """Normalize PostgreSQL session parameters for installer-friendly configuration.

    Allows installers to set e.g. METRICS_SERVICE_DATABASES__default__OPTIONS__datestyle="iso, mdy"
    without needing to know the psycopg-specific OPTIONS__options=-c datestyle=... syntax.

    Example:
        METRICS_SERVICE_DATABASES__default__OPTIONS__application_name="my service"
        becomes: OPTIONS['options'] = "-c application_name=my\\ service"

    Supported parameters:
        - datestyle: Date/time display format
        - search_path: Schema search order
        - timezone: Session timezone
        - application_name: Application identifier

    Note:
        - Session parameters are removed from OPTIONS to prevent duplicates
        - Values with spaces are automatically backslash-escaped per libpq requirements
        - Existing OPTIONS['options'] strings are preserved and extended
        - Returns a deep copy; does not mutate the input

    Args:
        databases: DATABASES setting dict

    Returns:
        Transformed databases dict with normalized PostgreSQL options

    Used as a Dynaconf Validator cast function, called during validation.
    """
    if not isinstance(databases, dict):
        return databases

    # Create deep copy to avoid mutating input
    databases = copy.deepcopy(databases)

    for db_name, db_conf in databases.items():
        if not isinstance(db_conf, dict):
            continue

        opts = db_conf.get("OPTIONS", {})
        if not isinstance(opts, dict):
            continue

        # Extract session params (case-insensitive matching)
        session_params = {}
        for key in list(opts.keys()):
            if key.lower() in SUPPORTED_PG_SESSION_PARAMS:
                session_params[key] = opts.pop(key)

        if not session_params:
            continue

        try:
            # Build PostgreSQL -c options with backslash-escaped spaces (libpq requirement)
            pg_opts = [f"-c {k}={str(v).replace(' ', r'\ ')}" for k, v in session_params.items()]

            # Preserve existing options and append new ones
            existing = opts.get("options", "")
            opts["options"] = f"{existing} {' '.join(pg_opts)}".strip()

            logger.debug(
                f"Normalized PostgreSQL session parameters for database '{db_name}': {list(session_params.keys())}"
            )
        except Exception as e:
            # Don't break settings loading on normalization errors
            logger.warning(
                f"Failed to normalize PostgreSQL options for database '{db_name}': {e}. "
                f"Session parameters: {session_params}"
            )
            # Restore the parameters to OPTIONS so they're not lost
            opts.update(session_params)

    return databases


# Framework-provided validators for installer-friendly configuration
framework_validators = [
    Validator(
        "DATABASES",
        cast=_normalize_postgresql_options,
        description="Normalize PostgreSQL session parameters to -c format in OPTIONS['options']",
    ),
]
"""Validators that normalize environment variables for better installer experience.

These validators transform environment variables into the format required by underlying libraries.
For example, PostgreSQL session parameters like 'datestyle' are transformed into the -c flag
format required by psycopg.
"""
