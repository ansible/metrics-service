"""
Post-load settings processing for metrics_service.
This module performs validation and dynamic configuration after all settings
are loaded.
"""

import os
import logging
from django.conf import settings

# Validate required environment variables for production
if not getattr(settings, "DEBUG", True):
    required_env_vars = [
        "METRICS_SERVICE_SECRET_KEY",
        "METRICS_SERVICE_DB_HOST",
        "METRICS_SERVICE_DB_USER",
        "METRICS_SERVICE_DB_PASSWORD",
        "METRICS_SERVICE_DB_NAME",
    ]

    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    if missing_vars:
        vars_str = ", ".join(missing_vars)
        error_msg = f"Missing required environment variables: {vars_str}"
        raise ValueError(error_msg)

# Ensure SECRET_KEY is set
if not getattr(settings, "SECRET_KEY", None):
    raise ValueError("SECRET_KEY must be set")

# Process ALLOWED_HOSTS if it's a string
allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
if isinstance(allowed_hosts, str):
    ALLOWED_HOSTS = [host.strip() for host in allowed_hosts.split(",") if host.strip()]

# Process CORS_ALLOWED_ORIGINS if it's a string
cors_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
if isinstance(cors_origins, str):
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

# Validate database configuration
databases = getattr(settings, "DATABASES", {})
db_config = databases.get("default", {})
if db_config.get("ENGINE") == "django.db.backends.postgresql":
    required_db_fields = ["HOST", "USER", "PASSWORD", "NAME"]
    missing_db_fields = [field for field in required_db_fields if not db_config.get(field)]
    if missing_db_fields and not getattr(settings, "DEBUG", True):
        raise ValueError(f"Missing required database fields: {', '.join(missing_db_fields)}")

# Process feature flags from environment
feature_flags = getattr(settings, "FEATURE_FLAGS", {})
for flag_name in feature_flags.keys():
    env_var = f"METRICS_SERVICE_{flag_name}"
    if os.environ.get(env_var):
        feature_flags[flag_name] = os.environ.get(env_var, "false").lower() == "true"

# Configure OAuth2 settings if enabled
installed_apps = getattr(settings, "INSTALLED_APPS", [])
if "ansible_base.oauth2_provider" in installed_apps:
    OAUTH2_PROVIDER = {
        "SCOPES": {
            "read": "Read access",
            "write": "Write access",
        },
        "ACCESS_TOKEN_EXPIRE_SECONDS": int(os.environ.get("METRICS_SERVICE_OAUTH2_ACCESS_TOKEN_EXPIRE", "3600")),
        "REFRESH_TOKEN_EXPIRE_SECONDS": int(os.environ.get("METRICS_SERVICE_OAUTH2_REFRESH_TOKEN_EXPIRE", "3600")),
    }

# Configure JWT settings if enabled
if getattr(settings, "JWT_CONSUMER_ENABLED", False):
    JWT_CONSUMER = {
        "JWT_SECRET_KEY": getattr(settings, "SECRET_KEY"),
        "JWT_ALGORITHM": getattr(settings, "JWT_CONSUMER_ALGORITHM", "HS256"),
        "JWT_EXPIRATION_DELTA": int(os.environ.get("METRICS_SERVICE_JWT_EXPIRATION", "3600")),
    }

# Configure dispatcherd if enabled
if feature_flags.get("DISPATCHERD_ENABLED"):
    DISPATCHERD_CONFIG = {
        "workers": int(os.environ.get("METRICS_SERVICE_DISPATCHERD_WORKERS", "4")),
        "max_tasks_per_worker": int(os.environ.get("METRICS_SERVICE_DISPATCHERD_MAX_TASKS", "100")),
        "task_timeout": int(os.environ.get("METRICS_SERVICE_DISPATCHERD_TIMEOUT", "3600")),
    }

# Log configuration summary
logger = logging.getLogger(__name__)
logger.info(f"Debug mode: {getattr(settings, 'DEBUG', False)}")
logger.info(f"Database engine: {db_config.get('ENGINE', 'not configured')}")
logger.info(f"Feature flags: {list(feature_flags.keys())}")
