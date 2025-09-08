"""
Base Django settings for metrics_service following AAP standards.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("METRICS_SERVICE_SECRET_KEY", "dev-secret-key-change-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]

# Service identification for AAP
SERVICE_TYPE = "metrics-service"
SERVICE_ID = os.environ.get("METRICS_SERVICE_ID", "generated-uuid")

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "oauth2_provider",
    "social_django",
]

# DAB apps - For immediate setup without complex dependencies
# Full AAP features available when installing with: pip install -e ".[dev]"
DAB_APPS = [
    "ansible_base",
    # These are the core apps that work without additional dependencies
    "ansible_base.rest_filters",  # Add when needed
    "ansible_base.rest_pagination",  # Add when needed
    "ansible_base.rbac",  # Add when needed
    "ansible_base.authentication",  # Add when needed
    # "ansible_base.oauth2_provider",  # Temporarily disabled due to model conflicts
    "ansible_base.activitystream",  # Add when needed
    "ansible_base.jwt_consumer",  # Add when needed
    "ansible_base.resource_registry",  # Add when needed
    # "ansible_base.feature_flags",  # Temporarily disabled due to missing 'flags' module
]

# Uncomment the line below to enable all DAB features with development setup
# DAB_APPS = [app.strip("# ") for app in [
#     "ansible_base.rest_filters",
#     "ansible_base.rest_pagination",
#     "ansible_base.rbac",
#     "ansible_base.authentication",
#     "ansible_base.oauth2_provider",
#     "ansible_base.activitystream",
#     "ansible_base.jwt_consumer",
#     "ansible_base.resource_registry",
#     "ansible_base.feature_flags",
# ]]

LOCAL_APPS = [
    "apps.core",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + DAB_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "ansible_base.authentication.middleware.AuthenticatorBackendMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "ansible_base.lib.middleware.logging.LogRequestMiddleware",
    "ansible_base.lib.middleware.logging.LogTracebackMiddleware",
]

ROOT_URLCONF = "metrics_service.urls"

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

WSGI_APPLICATION = "metrics_service.wsgi.application"
ASGI_APPLICATION = "metrics_service.asgi.application"

# Database
# Default to SQLite for immediate development, override with environment variables for production
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("METRICS_SERVICE_DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("METRICS_SERVICE_DB_NAME", BASE_DIR / "db.sqlite3"),
        "HOST": os.environ.get("METRICS_SERVICE_DB_HOST", ""),
        "PORT": os.environ.get("METRICS_SERVICE_DB_PORT", ""),
        "USER": os.environ.get("METRICS_SERVICE_DB_USER", ""),
        "PASSWORD": os.environ.get("METRICS_SERVICE_DB_PASSWORD", ""),
        "OPTIONS": {},
    }
}

# Override for PostgreSQL when environment variables are set
if os.environ.get("METRICS_SERVICE_DB_ENGINE") == "django.db.backends.postgresql":
    DATABASES["default"].update(
        {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ.get("METRICS_SERVICE_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("METRICS_SERVICE_DB_PORT", "55432"),
            "USER": os.environ.get("METRICS_SERVICE_DB_USER", "metrics_service"),
            "PASSWORD": os.environ.get("METRICS_SERVICE_DB_PASSWORD", "metrics_service"),
            "NAME": os.environ.get("METRICS_SERVICE_DB_NAME", "metrics_service"),
            "OPTIONS": {
                "sslmode": os.environ.get("METRICS_SERVICE_DB_SSLMODE", "prefer"),
            },
        }
    )

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "core.User"

# Django REST Framework Configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# OpenAPI/Swagger Documentation
SPECTACULAR_SETTINGS = {
    "TITLE": "Metrics Service API",
    "DESCRIPTION": "API documentation for Metrics Service",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v[0-9]",
    "SCHEMA_PATH_PREFIX_TRIM": True,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
    },
}

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = True  # Only for development
CORS_ALLOWED_ORIGINS = []  # Set in production

# Django-Ansible-Base Configuration
ANSIBLE_BASE_TEAM_MODEL = "core.Team"
ANSIBLE_BASE_ORGANIZATION_MODEL = "core.Organization"
ANSIBLE_BASE_RESOURCE_CONFIG_MODULE = "apps.core.resource_api"
ANSIBLE_BASE_USER_VIEWSET = "apps.api.v1.views.UserViewSet"

# RBAC Configuration
ANSIBLE_BASE_ALLOW_SINGLETON_USER_ROLES = True
ANSIBLE_BASE_ALLOW_SINGLETON_TEAM_ROLES = True
ALLOW_SHARED_RESOURCE_CUSTOM_ROLES = True
ALLOW_LOCAL_ASSIGNING_JWT_ROLES = True  # Set to False with resource server

# Authentication Backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # Default Django auth
    "ansible_base.authentication.backend.AnsibleBaseAuth",
]

# JWT Consumer Configuration
JWT_CONSUMER_ENABLED = True
JWT_CONSUMER_ALGORITHM = "HS256"

# Resource Server Configuration
RESOURCE_SERVER = {
    # 'URL': 'https://aap-gw-proxy-1:9080',
    # 'SECRET_KEY': '<service key>',
    # 'VALIDATE_HTTPS': False,
}
RESOURCE_SERVER_SYNC_ENABLED = False

# Background Task Configuration (Dispatcherd)
DISPATCHERD_ENABLED = os.environ.get("METRICS_SERVICE_DISPATCHERD_ENABLED", "false").lower() == "true"

# Feature Flags
FEATURE_FLAGS = {
    "DISPATCHERD_ENABLED": DISPATCHERD_ENABLED,
}

# OAuth2 Provider Configuration
OAUTH2_PROVIDER_APPLICATION_MODEL = "oauth2_provider.Application"
OAUTH2_PROVIDER_ID_TOKEN_MODEL = "oauth2_provider.IDToken"
OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL = "oauth2_provider.AccessToken"
OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL = "oauth2_provider.RefreshToken"
OAUTH2_PROVIDER = {
    "SCOPES": {
        "read": "Read access",
        "write": "Write access",
    },
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    "REFRESH_TOKEN_EXPIRE_SECONDS": 86400,
}

# Ansible Base RBAC Model Registry
ANSIBLE_BASE_RBAC_MODEL_REGISTRY = {}
ANSIBLE_BASE_MANAGED_ROLE_REGISTRY = {}

# Cache Configuration
# Default to local memory cache for development, override for production
CACHES = {
    "default": {
        "BACKEND": os.environ.get("METRICS_SERVICE_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": os.environ.get("METRICS_SERVICE_CACHE_LOCATION", "default"),
    }
}

# Override for Redis when environment variable is set
if os.environ.get("METRICS_SERVICE_REDIS_URL"):
    CACHES["default"] = {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("METRICS_SERVICE_REDIS_URL"),
    }

# Session Configuration
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Logging Configuration (will be enhanced in post_load.py)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "ansible_base.lib.logging.filters.RequestIdFilter",
        },
    },
    "formatters": {
        "simple": {
            "format": "{asctime} {levelname:<8} {name} {message}",
            "style": "{",
        },
        "verbose": {
            "format": "{asctime} {levelname:<8} [{request_id}] {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_id"],
        },
    },
    "loggers": {
        "ansible_base": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "metrics_service": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": True,
        },
    },
}

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
