from django.apps import AppConfig


class MetricsStorageConfig(AppConfig):
    """App configuration for metrics storage in SQLite database."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.metrics_storage"
    verbose_name = "Metrics Storage"
