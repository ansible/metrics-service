"""Tests for the trace-propagating Gateway API client."""

import time
import uuid
from pathlib import Path

import pytest
from ansible_base.resource_registry.rest_client import ResourceAPIClient

from apps.core import gateway_client
from apps.core.gateway_client import TracePropagatingResourceAPIClient, create_traced_api_client
from apps.core.request_context import REQUEST_ID_HEADER, TRACEPARENT_HEADER, request_context

VALID_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def _client() -> TracePropagatingResourceAPIClient:
    client = TracePropagatingResourceAPIClient(
        service_url="https://gateway.example.com", service_path="/api/v1/service-index/"
    )
    # Seed the cached service token so building the headers does not touch the DB.
    client._jwt = "service-token"
    client._jwt_timeout = time.time() + 300
    return client


@pytest.mark.unit
def test_client_merges_request_id_without_dropping_auth_header():
    request_id = str(uuid.uuid4())

    with request_context(request_id, VALID_TRACEPARENT):
        headers = _client().requests_auth_kwargs["headers"]

    assert headers["X-ANSIBLE-SERVICE-AUTH"] == "service-token"
    assert headers[REQUEST_ID_HEADER] == request_id
    assert headers[TRACEPARENT_HEADER] == VALID_TRACEPARENT


@pytest.mark.unit
def test_client_only_sends_auth_header_without_context():
    headers = _client().requests_auth_kwargs["headers"]

    assert headers == {"X-ANSIBLE-SERVICE-AUTH": "service-token"}


@pytest.mark.unit
def test_client_is_a_resource_api_client():
    assert isinstance(_client(), ResourceAPIClient)


@pytest.mark.unit
def test_create_traced_api_client_builds_subclass_from_settings(settings):
    """The factory must derive every constructor argument from settings."""
    settings.RESOURCE_SERVICE_PATH = "/api/v1/service-index/"
    settings.RESOURCE_SERVER = {"URL": "https://gateway.example.com", "SECRET_KEY": "secret", "VALIDATE_HTTPS": True}
    settings.RESOURCE_SYNC_JWT_EXPIRATION = 300

    client = create_traced_api_client()

    assert isinstance(client, TracePropagatingResourceAPIClient)
    assert client.base_url == "https://gateway.example.com/api/v1/service-index/"
    assert client.verify_https is True
    assert client.raise_if_bad_request is False
    assert client.jwt_expiration == 300


@pytest.mark.unit
def test_create_traced_api_client_forwards_the_same_kwargs_as_dab(settings, monkeypatch):
    """
    Guard against drift from DAB's ``create_api_client``.

    ``create_traced_api_client`` re-implements DAB's factory so it can swap the
    client class. If DAB adds or renames a parameter, this copy would silently
    stop forwarding it, so pin the argument dicts against each other.
    """
    from ansible_base.resource_registry.tasks import sync as dab_sync

    from apps.core import gateway_client

    settings.RESOURCE_SERVICE_PATH = "/api/v1/service-index/"
    settings.RESOURCE_SERVER = {"URL": "https://gateway.example.com", "SECRET_KEY": "secret", "VALIDATE_HTTPS": True}
    settings.RESOURCE_JWT_USER_ID = None
    settings.RESOURCE_SYNC_JWT_EXPIRATION = 300

    captured: dict[str, dict] = {}

    def _record(name):
        def record(**kwargs):
            captured[name] = kwargs
            return object()

        return record

    monkeypatch.setattr(dab_sync, "get_resource_server_client", _record("dab"))
    monkeypatch.setattr(gateway_client, "TracePropagatingResourceAPIClient", _record("traced"))

    dab_sync.create_api_client()
    gateway_client.create_traced_api_client()

    # Our factory builds the URL/verify_https itself, exactly as
    # get_resource_server_client() does, so only the forwarded kwargs are compared.
    traced = {k: v for k, v in captured["traced"].items() if k not in {"service_url", "verify_https", "service_path"}}
    dab = {k: v for k, v in captured["dab"].items() if k != "service_path"}

    assert traced == dab


@pytest.mark.unit
def test_no_unwired_dab_api_client_call_sites():
    """
    Every DAB ``create_api_client()`` caller must go through the traced factory.

    A new call site that builds a bare ``ResourceAPIClient`` would silently drop
    the propagation headers, and nothing else would fail.
    """
    apps_dir = Path(gateway_client.__file__).resolve().parents[1]
    offenders = sorted(
        str(path.relative_to(apps_dir))
        for path in apps_dir.rglob("*.py")
        if "create_api_client(" in path.read_text(encoding="utf-8") and path.name != "gateway_client.py"
    )

    assert offenders == []


@pytest.mark.unit
def test_create_traced_api_client_requires_service_path(settings):
    settings.RESOURCE_SERVICE_PATH = None

    with pytest.raises(ValueError, match="RESOURCE_SERVICE_PATH"):
        create_traced_api_client()
