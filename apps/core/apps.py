"""
Core app configuration for metrics_service.
"""

from ansible_base.rbac.permission_registry import permission_registry
from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration for the core app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        """Initialize app when Django starts."""
        # Import signals to ensure they are registered
        from . import signals  # noqa: F401

        # Register models with DAB permission registry
        self._register_dab_permissions()

    def _register_dab_permissions(self):
        """Register models with DAB's permission registry."""
        try:
            # Import models here to avoid circular imports
            from .models import Organization, Team, User

            # Register models with their hierarchical relationships
            permission_registry.register(Organization, parent_field_name=None)
            permission_registry.register(User, parent_field_name=None)
            permission_registry.register(Team, parent_field_name="organization")

        except ImportError:
            # DAB not available - skip registration
            pass
        except Exception as e:
            # Models might already be registered or other DAB setup issues
            from metrics_service.logger import get_logger

            logger = get_logger(__name__)
            logger.warning(f"DAB permission registry registration failed: {e}")
