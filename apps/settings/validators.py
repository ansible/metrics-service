"""Dynaconf validators that executes only on non-development environments."""

from dynaconf import Validator

validators = [
    # Security: Require SECRET_KEY to be explicitly set (not defaults)
    # Note: Validators only run in production (validation=False in development at export time)
    Validator(
        "SECRET_KEY",
        must_exist=True,
        condition=lambda value: not value.startswith(("django-insecure", "dev-secret", "PRODUCTION-")),
        messages={
            "condition": "Set METRICS_SERVICE_SECRET_KEY as an environment variable.",
        },
    ),
    Validator(
        "SEGMENT_WRITE_KEY",
        must_exist=True,
        ne="test-segment-write-key-change-in-production",  # Default test key
        messages={
            "operations": "SEGMENT_WRITE_KEY must not use default value in production.",
        },
    ),
    # Database: Ensure critical database settings exist
    Validator("DATABASES.default.NAME", must_exist=True),
    Validator("DATABASES.default.HOST", must_exist=True),
    Validator("DATABASES.default.USER", must_exist=True),
    Validator("DATABASES.default.PASSWORD", must_exist=True),
]
