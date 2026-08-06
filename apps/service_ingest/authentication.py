"""DAB JWT-based authentication for the service ingest endpoint.

Services authenticate using a Gateway-issued X-DAB-JW-TOKEN JWT, obtained via
the Gateway WIT endpoint (POST /api/gateway/v1/workload_identity_tokens/).

The JWT is validated by DAB's JWTCommonAuth using the shared gateway public key
(RESOURCE_SERVER__SECRET_KEY / ANSIBLE_BASE_JWT_KEY).
"""

import logging

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class IngestJWTAuthentication(BaseAuthentication):
    """
    Validates X-DAB-JW-TOKEN JWTs issued by the AAP Gateway.

    On success returns (user, token) where user is the DAB-synced gateway
    system user. The service_name is NOT extracted from the JWT here — it
    comes from the request body and is validated against ServiceDefinition
    in the view/serializer layer (the JWT proves the caller is a legitimate
    AAP service; the service_name field identifies which one).
    """

    def authenticate(self, request):
        token_header = request.headers.get("X-DAB-JW-TOKEN")
        if not token_header:
            return None  # no credentials; let other authenticators try

        try:
            from ansible_base.jwt_consumer.common.auth import JWTCommonAuth

            jwt_auth = JWTCommonAuth()
            jwt_auth.parse_jwt_token(request)
        except Exception as exc:
            logger.debug("JWT parse failed: %s", exc)
            raise AuthenticationFailed("Invalid or expired JWT token") from exc

        if jwt_auth.user is None:
            raise AuthenticationFailed("JWT authentication produced no user")

        logger.debug("Authenticated ingest request via DAB JWT (user=%s)", jwt_auth.user)
        return (jwt_auth.user, jwt_auth.token)

    def authenticate_header(self, request) -> str:
        return "X-DAB-JW-TOKEN"
