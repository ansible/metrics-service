"""
Resource API configuration for Django-Ansible-Base resource registry.
"""

from django.contrib.auth import get_user_model

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

# Register authentication models as non-shared resources
try:
    from ansible_base.authentication.models import Authenticator

    RESOURCE_LIST.append(
        ResourceConfig(
            Authenticator,
            # Don't share authenticator models across services
        )
    )
except ImportError:
    pass

# # Register other ansible_base models as needed
# try:
#     from ansible_base.oauth2_provider.models import OAuth2Application, OAuth2AccessToken

#     RESOURCE_LIST.extend(
#         [
#             ResourceConfig(OAuth2Application),
#             ResourceConfig(OAuth2AccessToken),
#         ]
#     )
# except ImportError:
#     pass

try:
    from ansible_base.rbac.models import RoleDefinition

    RESOURCE_LIST.append(ResourceConfig(RoleDefinition))
except ImportError:
    pass
