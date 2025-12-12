"""
Resource API configuration for Django-Ansible-Base resource registry.
"""

from ansible_base.resource_registry.registry import (
    ResourceConfig,
    ServiceAPIConfig,
    SharedResource,
)
from ansible_base.resource_registry.shared_types import (
    OrganizationType,
    TeamType,
    UserType,
)
from django.conf import settings
from django.contrib.auth import get_user_model

from .models import Organization, Team


class APIConfig(ServiceAPIConfig):
    service_type = "metrics_service"


# Service resource configuration for AAP resource sharing
RESOURCE_LIST = [
    ResourceConfig(
        get_user_model(),
        shared_resource=SharedResource(serializer=UserType, is_provider=True),
        name_field="username",
    ),
    ResourceConfig(
        Team,
        shared_resource=SharedResource(serializer=TeamType, is_provider=False),
    ),
    ResourceConfig(
        Organization,
        shared_resource=SharedResource(serializer=OrganizationType, is_provider=False),
    ),
]

try:
    from ansible_base.rbac.models import RoleDefinition

    RESOURCE_LIST.append(ResourceConfig(RoleDefinition))
except ImportError:
    pass


def service_metadata() -> dict:
    """
    Get service metadata for resource registry.

    Returns:
        dict: Service metadata
    """
    try:
        return {
            "service_type": "metrics_service",
            "system_uuid": getattr(settings, "SYSTEM_UUID", "unknown"),
            "version": "1.0.0",
        }
    except Exception:
        return {"service_type": "metrics_service", "system_uuid": "unknown", "version": "1.0.0"}
