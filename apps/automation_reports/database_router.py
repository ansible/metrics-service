"""
Database router for Automation Reports app.

Routes all automation_reports queries to the 'metrics_storage' SQLite database.
Tables are prefixed with 'ar_' to differentiate from metrics_storage tables.
"""


class AutomationReportsRouter:
    """
    Database router to direct automation_reports app queries to SQLite database.

    All models in the automation_reports app will use the same 'metrics_storage'
    SQLite database as the metrics_storage app, but with different table names.
    """

    route_app_labels = {"automation_reports"}

    def db_for_read(self, model, **hints):
        """
        Point read operations for automation_reports models to SQLite.
        """
        if model._meta.app_label in self.route_app_labels:
            return "metrics_storage"
        return None

    def db_for_write(self, model, **hints):
        """
        Point write operations for automation_reports models to SQLite.
        """
        if model._meta.app_label in self.route_app_labels:
            return "metrics_storage"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations between automation_reports and metrics_storage models.
        """
        if obj1._meta.app_label in self.route_app_labels or obj2._meta.app_label in self.route_app_labels:
            # Allow relations between automation_reports and metrics_storage
            return obj1._meta.app_label in {"automation_reports", "metrics_storage"} and obj2._meta.app_label in {
                "automation_reports",
                "metrics_storage",
            }
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Ensure automation_reports migrations only run on the metrics_storage SQLite database.
        """
        if app_label in self.route_app_labels:
            return db == "metrics_storage"
        return None
