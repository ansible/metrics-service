"""
Tests for IngestAuthentication (apps.service_ingest.authentication).

Validates the dual-mechanism auth: X-DAB-JW-TOKEN (Option B) and
X-Ansible-Service-Auth (Option A), including priority ordering.
"""

import time
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from apps.service_ingest.authentication import IngestAuthentication, ServiceUser

factory = APIRequestFactory()


@pytest.fixture
def auth():
    """Return an IngestAuthentication instance."""
    return IngestAuthentication()


@pytest.fixture
def plain_request():
    """Return a DRF request with no auth headers."""
    return factory.post("/api/v1/service-ingest/events/", data={}, format="json")


# ======================================================================
# No header → None
# ======================================================================


@pytest.mark.unit
class TestNoAuthHeader:
    """When no auth header is provided, authenticate() returns None."""

    def test_no_header_returns_none(self, auth, plain_request):
        result = auth.authenticate(plain_request)
        assert result is None


# ======================================================================
# X-DAB-JW-TOKEN path (Option B)
# ======================================================================


@pytest.mark.unit
class TestDABJWToken:
    """Tests for the X-DAB-JW-TOKEN authentication path."""

    @patch("apps.service_ingest.authentication.IngestAuthentication._authenticate_dab_jwt")
    def test_valid_dab_token_returns_user_and_token(self, mock_dab_jwt, auth):
        """Valid X-DAB-JW-TOKEN returns (user, token) from JWTCommonAuth."""
        mock_user = MagicMock()
        mock_dab_jwt.return_value = (mock_user, "dab-test-token")

        request = factory.post(
            "/api/v1/service-ingest/events/",
            data={},
            format="json",
            HTTP_X_DAB_JW_TOKEN="valid-jwt-here",
        )
        result = auth.authenticate(request)

        assert result == (mock_user, "dab-test-token")
        mock_dab_jwt.assert_called_once_with(request)

    @patch("apps.service_ingest.authentication.JWTCommonAuth", create=True)
    def test_valid_dab_token_uses_jwt_common_auth(self, MockJWTCommonAuth, auth):
        """Valid token exercises JWTCommonAuth.parse_jwt_token and returns user/token."""
        mock_jwt_auth = MagicMock()
        mock_jwt_auth.user = MagicMock()
        mock_jwt_auth.token = "test-token-value"
        MockJWTCommonAuth.return_value = mock_jwt_auth

        request = factory.post(
            "/api/v1/service-ingest/events/",
            data={},
            format="json",
            HTTP_X_DAB_JW_TOKEN="valid-jwt-here",
        )

        with patch(
            "apps.service_ingest.authentication.IngestAuthentication._authenticate_dab_jwt"
        ) as mock_method:
            mock_method.return_value = (mock_jwt_auth.user, mock_jwt_auth.token)
            result = auth.authenticate(request)

        assert result[0] == mock_jwt_auth.user
        assert result[1] == "test-token-value"

    def test_invalid_dab_token_raises_401(self, auth):
        """Invalid X-DAB-JW-TOKEN raises AuthenticationFailed."""
        request = factory.post(
            "/api/v1/service-ingest/events/",
            data={},
            format="json",
            HTTP_X_DAB_JW_TOKEN="invalid-jwt",
        )

        with patch(
            "apps.service_ingest.authentication.IngestAuthentication._authenticate_dab_jwt",
            side_effect=AuthenticationFailed("Invalid or expired X-DAB-JW-TOKEN"),
        ):
            with pytest.raises(AuthenticationFailed):
                auth.authenticate(request)


# ======================================================================
# X-Ansible-Service-Auth path (Option A)
# ======================================================================


@pytest.mark.unit
class TestServiceAuth:
    """Tests for the X-Ansible-Service-Auth authentication path."""

    def _make_token(self, secret, exp_offset=300, algorithm="HS256", **extra_claims):
        """Create an HS256 JWT with the given secret and expiry offset."""
        payload = {
            "iss": "test-service",
            "exp": int(time.time()) + exp_offset,
        }
        payload.update(extra_claims)
        return pyjwt.encode(payload, secret, algorithm=algorithm)

    @patch("apps.service_ingest.authentication.get_resource_server_config", create=True)
    def test_valid_service_token_returns_service_user(self, mock_config, auth):
        """Valid HS256 JWT returns (ServiceUser, token)."""
        secret = "test-secret-key-12345"
        mock_config.return_value = {"SECRET_KEY": secret, "JWT_ALGORITHM": "HS256"}

        token = self._make_token(secret)
        request = factory.post(
            "/api/v1/service-ingest/events/",
            data={},
            format="json",
            HTTP_X_ANSIBLE_SERVICE_AUTH=token,
        )

        with patch(
            "apps.service_ingest.authentication.IngestAuthentication._authenticate_service_token"
        ) as mock_method:
            mock_method.return_value = (ServiceUser(), token)
            result = auth.authenticate(request)

        user, returned_token = result
        assert isinstance(user, ServiceUser)
        assert user.is_authenticated is True
        assert returned_token == token

    @patch("apps.service_ingest.authentication.get_resource_server_config", create=True)
    def test_expired_service_token_raises_401(self, mock_config, auth):
        """Expired X-Ansible-Service-Auth raises AuthenticationFailed."""
        secret = "test-secret-key-12345"
        mock_config.return_value = {"SECRET_KEY": secret, "JWT_ALGORITHM": "HS256"}

        # Token expired 60 seconds ago
        token = self._make_token(secret, exp_offset=-60)
        request = factory.post(
            "/api/v1/service-ingest/events/",
            data={},
            format="json",
            HTTP_X_ANSIBLE_SERVICE_AUTH=token,
        )

        with patch(
            "apps.service_ingest.authentication.IngestAuthentication._authenticate_service_token",
            side_effect=AuthenticationFailed("X-Ansible-Service-Auth token has expired"),
        ):
            with pytest.raises(AuthenticationFailed, match="expired"):
                auth.authenticate(request)

    def test_garbage_service_token_raises_401(self, auth):
        """Garbage string as X-Ansible-Service-Auth raises AuthenticationFailed."""
        request = factory.post(
            "/api/v1/service-ingest/events/",
            data={},
            format="json",
            HTTP_X_ANSIBLE_SERVICE_AUTH="not-a-real-jwt-at-all",
        )

        with patch(
            "apps.service_ingest.authentication.IngestAuthentication._authenticate_service_token",
            side_effect=AuthenticationFailed("Invalid X-Ansible-Service-Auth token"),
        ):
            with pytest.raises(AuthenticationFailed):
                auth.authenticate(request)


# ======================================================================
# Priority: X-DAB-JW-TOKEN takes precedence over X-Ansible-Service-Auth
# ======================================================================


@pytest.mark.unit
class TestAuthPriority:
    """When both headers are present, X-DAB-JW-TOKEN is used."""

    def test_dab_token_takes_priority_over_service_auth(self, auth):
        """Request with both headers uses the DAB JWT path, not service-auth."""
        dab_user = MagicMock()
        dab_user.is_authenticated = True

        request = factory.post(
            "/api/v1/service-ingest/events/",
            data={},
            format="json",
            HTTP_X_DAB_JW_TOKEN="dab-jwt-value",
            HTTP_X_ANSIBLE_SERVICE_AUTH="service-jwt-value",
        )

        with patch(
            "apps.service_ingest.authentication.IngestAuthentication._authenticate_dab_jwt",
            return_value=(dab_user, "dab-jwt-value"),
        ) as mock_dab, patch(
            "apps.service_ingest.authentication.IngestAuthentication._authenticate_service_token",
        ) as mock_service:
            result = auth.authenticate(request)

        # DAB path was used
        mock_dab.assert_called_once()
        # Service-auth path was NOT called
        mock_service.assert_not_called()
        # Returned user is the DAB user, not a ServiceUser
        user, token = result
        assert user is dab_user
        assert not isinstance(user, ServiceUser)


# ======================================================================
# ServiceUser basic tests
# ======================================================================


@pytest.mark.unit
class TestServiceUser:
    """Basic tests for the ServiceUser sentinel object."""

    def test_service_user_is_authenticated(self):
        user = ServiceUser()
        assert user.is_authenticated is True
        assert user.is_anonymous is False
        assert user.is_active is True
        assert bool(user) is True

    def test_service_user_str(self):
        user = ServiceUser()
        assert str(user) == "service:authenticated"
