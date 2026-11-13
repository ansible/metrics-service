"""Gateway API client that propagates the current request context.

DAB's ``ResourceAPIClient`` builds every outbound request from a single
overridable property, ``requests_auth_kwargs``. Subclassing it and merging in
``outbound_headers()`` attaches ``X-Request-ID`` (and a pass-through
``traceparent``) to all Gateway calls without patching DAB or any global state.

This subclass can be deleted if DAB ever grows native header support.
"""

from ansible_base.resource_registry.resource_server import get_resource_server_config
from ansible_base.resource_registry.rest_client import ResourceAPIClient
from ansible_base.resource_registry.tasks.sync import DEFAULT_SYNC_JWT_EXPIRATION
from django.conf import settings

from apps.core.request_context import outbound_headers


class TracePropagatingResourceAPIClient(ResourceAPIClient):
    """``ResourceAPIClient`` that adds request-context headers to every call."""

    @property
    def requests_auth_kwargs(self) -> dict:
        auth = super().requests_auth_kwargs
        headers = dict(auth.get("headers", {}))
        headers.update(outbound_headers())
        return {**auth, "headers": headers}


def create_traced_api_client(jwt_user_id: str | None = None) -> TracePropagatingResourceAPIClient:
    """Build a Gateway client from settings, mirroring DAB's ``create_api_client``.

    Args:
        jwt_user_id: Ansible ID to make requests as. Defaults to
            ``settings.RESOURCE_JWT_USER_ID``.
    """
    params: dict = {"raise_if_bad_request": False}

    if jwt_user_id is not None:
        params["jwt_user_id"] = jwt_user_id
    elif configured_user_id := getattr(settings, "RESOURCE_JWT_USER_ID", None):
        params["jwt_user_id"] = configured_user_id

    service_path = getattr(settings, "RESOURCE_SERVICE_PATH", None)
    if not service_path:
        raise ValueError("RESOURCE_SERVICE_PATH is not set.")
    params["service_path"] = service_path
    params["jwt_expiration"] = getattr(settings, "RESOURCE_SYNC_JWT_EXPIRATION", DEFAULT_SYNC_JWT_EXPIRATION)

    config = get_resource_server_config()
    return TracePropagatingResourceAPIClient(
        service_url=config["URL"],
        verify_https=config["VALIDATE_HTTPS"],
        **params,
    )
