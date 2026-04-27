from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration for the core app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        """Connect signals and RBAC post-migrate hooks on app startup."""
        from ansible_base.rbac.triggers import dab_post_migrate

        from . import signals  # noqa: F401

        dab_post_migrate.connect(
            self._create_managed_roles,
            dispatch_uid="core.create_managed_roles",
        )

    @staticmethod
    def _create_managed_roles(sender, **kwargs):
        """Create DAB-managed RBAC roles after each migration."""
        from ansible_base.rbac import permission_registry
        from django.apps import apps

        permission_registry.create_managed_roles(apps)
