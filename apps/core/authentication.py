"""Custom authentication classes for the service."""

from typing import Any

import jwt
from ansible_base.jwt_consumer.common.auth import JWTAuthentication
from ansible_base.resource_registry.models import service_id
from ansible_base.resource_registry.resource_server import get_resource_server_config
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request


class ServiceJWTAuthentication(JWTAuthentication):
    """JWT Authentication with RBAC permissions enabled."""

    use_rbac_permissions = True


class ServiceJWTAuthenticationNoRBAC(JWTAuthentication):
    """JWT Authentication without the RBAC claims-sync gateway fetch.

    Validates the DAB JWT (user resolution + is_superuser / resource_api_actions
    stamping) but skips process_rbac_permissions, avoiding the recursive
    jwt_claims call back to the gateway. Applied only to ServiceMetadataView so
    the gateway's populate_service_id probe can succeed while
    ServiceCluster.service_id is still NULL on 2.6->2.7 upgraded deployments.
    """

    use_rbac_permissions = False


class MetricsServiceTokenAuthentication(BaseAuthentication):
    """Authenticate service-to-service requests signed with this service's resource-server key."""

    def authenticate(self, request: Request) -> tuple[Any, str] | None:
        token = request.headers.get("X-ANSIBLE-SERVICE-AUTH")
        if not token:
            return None

        # A deployment without RESOURCE_SERVER__SECRET_KEY cannot sign or verify these tokens.
        # Reject the attempt rather than letting a KeyError surface as a 500 with a traceback.
        try:
            config = get_resource_server_config()
            secret_key = config["SECRET_KEY"]
        except KeyError as exc:
            raise AuthenticationFailed("Metrics Service token authentication is not configured") from exc

        try:
            claims = jwt.decode(
                token,
                secret_key,
                algorithms=[config.get("JWT_ALGORITHM", "HS256")],
                options={"require": ["iss", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed("Invalid Metrics Service token") from exc

        if claims["iss"] != str(service_id()):
            raise AuthenticationFailed("Metrics Service token issuer does not match this service")

        return None, "MetricsServiceTokenAuthentication"
