# """
# Production-specific settings for metrics_service.
# """

# import os
# from .defaults import *  # noqa: F401,F403

# # Production security settings
# DEBUG = False
# ALLOWED_HOSTS = os.environ.get("metrics_service_ALLOWED_HOSTS", "").split(",")

# # Database settings for production
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "HOST": os.environ.get("METRICS_SERVICE_DB_HOST"),
#         "PORT": os.environ.get("METRICS_SERVICE_DB_PORT", "55432"),
#         "USER": os.environ.get("METRICS_SERVICE_DB_USER"),
#         "PASSWORD": os.environ.get("METRICS_SERVICE_DB_PASSWORD"),
#         "NAME": os.environ.get("METRICS_SERVICE_DB_NAME"),
#         "OPTIONS": {
#             "sslmode": os.environ.get("METRICS_SERVICE_DB_SSLMODE", "require"),
#         },
#         "CONN_MAX_AGE": 60,
#     }
# }

# # Email settings for production
# EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# EMAIL_HOST = os.environ.get("metrics_service_EMAIL_HOST")
# EMAIL_PORT = int(os.environ.get("metrics_service_EMAIL_PORT", "587"))
# EMAIL_USE_TLS = os.environ.get("metrics_service_EMAIL_USE_TLS", "true").lower() == "true"
# EMAIL_HOST_USER = os.environ.get("metrics_service_EMAIL_USER")
# EMAIL_HOST_PASSWORD = os.environ.get("metrics_service_EMAIL_PASSWORD")
# DEFAULT_FROM_EMAIL = os.environ.get("metrics_service_FROM_EMAIL", "noreply@example.com")

# # CORS settings for production
# CORS_ALLOW_ALL_ORIGINS = False
# CORS_ALLOWED_ORIGINS = os.environ.get("metrics_service_CORS_ALLOWED_ORIGINS", "").split(",")
# CORS_ALLOW_CREDENTIALS = True

# # Cache settings for production
# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.redis.RedisCache",
#         "LOCATION": os.environ.get("metrics_service_REDIS_URL"),
#         "OPTIONS": {
#             "CONNECTION_POOL_KWARGS": {
#                 "max_connections": 20,
#                 "retry_on_timeout": True,
#             }
#         },
#     }
# }

# # Session configuration for production
# SESSION_ENGINE = "django.contrib.sessions.backends.cache"
# SESSION_CACHE_ALIAS = "default"
# SESSION_COOKIE_SECURE = True
# SESSION_COOKIE_HTTPONLY = True
# SESSION_COOKIE_AGE = 3600  # 1 hour

# # Security settings for production
# SECURE_SSL_REDIRECT = True
# SECURE_HSTS_SECONDS = 31536000  # 1 year
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True
# SECURE_CONTENT_TYPE_NOSNIFF = True
# SECURE_BROWSER_XSS_FILTER = True
# SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
# X_FRAME_OPTIONS = "DENY"
# CSRF_COOKIE_SECURE = True

# # Logging configuration for production
# LOGGING["handlers"]["file"] = {
#     "class": "logging.handlers.RotatingFileHandler",
#     "filename": "/var/log/metrics_service/metrics_service.log",
#     "maxBytes": 10485760,  # 10MB
#     "backupCount": 5,
#     "formatter": "json",
#     "filters": ["request_id"],
# }

# LOGGING["loggers"]["metrics_service"]["handlers"] = ["console", "file"]
# LOGGING["loggers"]["metrics_service"]["level"] = "INFO"
# LOGGING["loggers"]["ansible_base"]["level"] = "INFO"
# LOGGING["loggers"]["django"]["level"] = "WARNING"
# LOGGING["loggers"][""]["level"] = "ERROR"

# # Feature flags for production (disabled by default)
# FEATURE_FLAGS.update(
#     {
#         "DISPATCHERD_ENABLED": os.environ.get("metrics_service_DISPATCHERD_ENABLED", "false").lower() == "true",
#     }
# )

# # Static files for production
# STATIC_ROOT = "/var/www/metrics_service/static"
# MEDIA_ROOT = "/var/www/metrics_service/media"

# # Performance optimizations
# USE_TZ = True
# CONN_MAX_AGE = 60

# # Resource server for production
# if os.environ.get("metrics_service_RESOURCE_SERVER_URL"):
#     RESOURCE_SERVER = {
#         "URL": os.environ.get("metrics_service_RESOURCE_SERVER_URL"),
#         "SECRET_KEY": os.environ.get("metrics_service_RESOURCE_SERVER_SECRET"),
#         "VALIDATE_HTTPS": os.environ.get("metrics_service_RESOURCE_SERVER_VALIDATE_HTTPS", "true").lower() == "true",
#     }
#     RESOURCE_SERVER_SYNC_ENABLED = True
#     ALLOW_LOCAL_ASSIGNING_JWT_ROLES = False
