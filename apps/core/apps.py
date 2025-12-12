"""
Core app configuration for metrics_service.
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


def create_managed_roles_handler(sender, **kwargs):
    """
    Handler for dab_post_migrate signal to create managed roles.

    DAB sends the dab_post_migrate signal after migrations complete,
    but expects downstream apps to connect a handler that creates
    the managed roles defined in ANSIBLE_BASE_MANAGED_ROLE_REGISTRY.
    """
    from ansible_base.rbac.permission_registry import permission_registry
    from django.apps import apps

    try:
        permission_registry.create_managed_roles(apps, update_perms=True)
        logger.info("Created/updated managed RBAC roles")
    except Exception as e:
        logger.warning(f"Failed to create managed roles: {e}")


class CoreConfig(AppConfig):
    """Configuration for the core app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        """Initialize app when Django starts."""
        # Import signals to ensure they are registered
        from . import signals  # noqa: F401

        # Connect to dab_post_migrate to create managed roles after migrations
        self._connect_dab_post_migrate()

    def _connect_dab_post_migrate(self):
        """Connect to DAB's post-migrate signal to create managed roles."""
        try:
            from ansible_base.rbac.triggers import dab_post_migrate

            dab_post_migrate.connect(
                create_managed_roles_handler,
                dispatch_uid="apps.core.create_managed_roles",
            )
        except ImportError:
            # DAB not available - skip
            pass
