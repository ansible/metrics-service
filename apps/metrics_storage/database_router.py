"""
Database router for metrics_storage app.

Routes all database operations for the metrics_storage app to the dedicated
SQLite database (metricsStorage.sqlite) instead of the default PostgreSQL database.
"""


class MetricsStorageRouter:
    """
    A router to control all database operations on models in the metrics_storage application.

    All read/write operations for metrics_storage models are routed to the 'metrics_storage' database.
    This keeps metrics data isolated in a dedicated SQLite database separate from the main application data.
    """

    route_app_labels = {"metrics_storage"}

    def db_for_read(self, model, **hints):
        """
        Attempts to read metrics_storage models go to metrics_storage database.
        """
        if model._meta.app_label in self.route_app_labels:
            return "metrics_storage"
        return None

    def db_for_write(self, model, **hints):
        """
        Attempts to write metrics_storage models go to metrics_storage database.
        """
        if model._meta.app_label in self.route_app_labels:
            return "metrics_storage"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations if both models are in the metrics_storage app.
        """
        if obj1._meta.app_label in self.route_app_labels and obj2._meta.app_label in self.route_app_labels:
            return True
        # No opinion if neither model is in metrics_storage
        if obj1._meta.app_label not in self.route_app_labels and obj2._meta.app_label not in self.route_app_labels:
            return None
        # Block relations between metrics_storage and other apps
        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Ensure that the metrics_storage app's models only appear in the 'metrics_storage' database.
        """
        if app_label in self.route_app_labels:
            return db == "metrics_storage"
        # Other apps should not migrate to metrics_storage database
        if db == "metrics_storage":
            return False
        return None
