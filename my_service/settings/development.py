# """
# Development-specific settings for my_service.
# """

# from .defaults import *  # noqa: F401,F403

# # Override security settings for development
# DEBUG = True
# ALLOWED_HOSTS = ["*"]

# # Database settings for development
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "HOST": "127.0.0.1",
#         "PORT": "55432",
#         "USER": "my_service",
#         "PASSWORD": "my_service",
#         "NAME": "my_service_dev",
#         "OPTIONS": {
#             "sslmode": "disable",
#         },
#     }
# }

# # Email backend for development
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# # CORS settings for development
# CORS_ALLOW_ALL_ORIGINS = True
# CORS_ALLOW_CREDENTIALS = True

# # Cache settings for development (in-memory)
# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
#     }
# }

# # Session configuration for development
# SESSION_ENGINE = "django.contrib.sessions.backends.db"

# # Logging configuration for development
# LOGGING["loggers"]["my_service"]["level"] = "DEBUG"
# LOGGING["loggers"]["ansible_base"]["level"] = "DEBUG"
# LOGGING["loggers"]["django"]["level"] = "DEBUG"

# # Enable all feature flags for development
# FEATURE_FLAGS.update(
#     {
#         "DISPATCHERD_ENABLED": True,
#     }
# )

# # Development tools
# INSTALLED_APPS += [
#     "debug_toolbar",
# ]

# MIDDLEWARE += [
#     "debug_toolbar.middleware.DebugToolbarMiddleware",
# ]

# # Debug toolbar configuration
# INTERNAL_IPS = [
#     "127.0.0.1",
#     "localhost",
# ]


# # Disable migrations for faster testing
# class DisableMigrations:
#     def __contains__(self, item):
#         return True

#     def __getitem__(self, item):
#         return None


# # MIGRATION_MODULES = DisableMigrations()  # Uncomment to disable migrations
