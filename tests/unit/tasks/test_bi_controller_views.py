"""
Tests for BI connector Layer 2 API endpoints (live AWX DB).

Covers ControllerJobsView, ControllerHostsView, ControllerCredentialsView,
ControllerEventsView, and ControllerSnapshotView:
- Missing since/until params → 400
- Date range exceeding max window → 400 (7 days for most, 3 days for events)
- AWX DB unavailable → 503
- Collector exception → 500
- Valid request → 200 with data key
- Snapshot returns partial results when a collector fails
- Unauthenticated requests → 401/403
"""

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import User
from tests.test_utils import get_test_password

VALID_SINCE = "2025-03-01T00:00:00Z"
VALID_UNTIL_7 = "2025-03-07T23:59:59Z"  # 6 days — within 7-day limit
VALID_UNTIL_3 = "2025-03-03T23:59:59Z"  # 2 days — within 3-day limit
OVER_7_DAYS_UNTIL = "2025-03-10T00:00:00Z"  # 9 days — exceeds 7-day limit
OVER_3_DAYS_UNTIL = "2025-03-05T00:00:00Z"  # 4 days — exceeds 3-day limit

_HOURLY_PATCH = "apps.tasks.collectors.collect_hourly_metrics._get_hourly_collectors"
_SNAPSHOT_PATCH = "apps.tasks.collectors.collect_snapshot_metrics._get_snapshot_collectors"
_DB_PATCH = "apps.tasks.v1.controller_views.get_db_connection"


def _make_mock_collector(data=None):
    """Return a mock collector instance whose .gather() returns data."""
    mock = MagicMock()
    mock.gather.return_value = data or [{"id": 1, "name": "test"}]
    return mock


def _make_collectors_registry(collector_key: str, mock_collector):
    """Build a minimal collector registry dict for the given key."""
    return {collector_key: {"collector_func": lambda **kw: mock_collector}}


@pytest.mark.unit
@pytest.mark.django_db
class TestControllerJobsView(APITestCase):
    """Tests for GET /api/v1/controller/jobs/"""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.url = reverse("tasks:controller:controller-jobs")

    def test_unauthenticated_returns_401_or_403(self):
        response = self.client.get(self.url, {"since": VALID_SINCE, "until": VALID_UNTIL_7})
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_missing_since_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"until": VALID_UNTIL_7})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_until_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"since": VALID_SINCE})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_both_params_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_since_format_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"since": "not-a-date", "until": VALID_UNTIL_7})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_until_before_since_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"since": VALID_UNTIL_7, "until": VALID_SINCE})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_range_exceeding_7_days_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"since": VALID_SINCE, "until": OVER_7_DAYS_UNTIL})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "7 days" in str(response.data)

    def test_awx_db_unavailable_returns_503(self):
        self.client.force_authenticate(user=self.user)
        with patch(_DB_PATCH, side_effect=Exception("connection refused")):
            response = self.client.get(self.url, {"since": VALID_SINCE, "until": VALID_UNTIL_7})
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_collector_exception_returns_500(self):
        self.client.force_authenticate(user=self.user)
        mock_collector = MagicMock()
        mock_collector.gather.side_effect = Exception("query failed")
        registry = _make_collectors_registry("unified_jobs", mock_collector)

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_HOURLY_PATCH, return_value=registry):
            response = self.client.get(self.url, {"since": VALID_SINCE, "until": VALID_UNTIL_7})

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_valid_request_returns_200_with_data(self):
        self.client.force_authenticate(user=self.user)
        mock_collector = _make_mock_collector(data=[{"job_id": 1}])
        registry = _make_collectors_registry("unified_jobs", mock_collector)

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_HOURLY_PATCH, return_value=registry):
            response = self.client.get(self.url, {"since": VALID_SINCE, "until": VALID_UNTIL_7})

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert response.data["collector_type"] == "unified_jobs"
        assert "since" in response.data
        assert "until" in response.data


@pytest.mark.unit
@pytest.mark.django_db
class TestControllerHostsView(APITestCase):
    """Tests for GET /api/v1/controller/hosts/"""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.url = reverse("tasks:controller:controller-hosts")

    def test_missing_params_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_range_exceeding_7_days_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"since": VALID_SINCE, "until": OVER_7_DAYS_UNTIL})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_valid_request_returns_200(self):
        self.client.force_authenticate(user=self.user)
        mock_collector = _make_mock_collector()
        registry = _make_collectors_registry("job_host_summary_service", mock_collector)

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_HOURLY_PATCH, return_value=registry):
            response = self.client.get(self.url, {"since": VALID_SINCE, "until": VALID_UNTIL_7})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["collector_type"] == "job_host_summary_service"


@pytest.mark.unit
@pytest.mark.django_db
class TestControllerCredentialsView(APITestCase):
    """Tests for GET /api/v1/controller/credentials/"""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.url = reverse("tasks:controller:controller-credentials")

    def test_missing_params_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_valid_request_returns_200(self):
        self.client.force_authenticate(user=self.user)
        mock_collector = _make_mock_collector()
        registry = _make_collectors_registry("credentials_service", mock_collector)

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_HOURLY_PATCH, return_value=registry):
            response = self.client.get(self.url, {"since": VALID_SINCE, "until": VALID_UNTIL_7})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["collector_type"] == "credentials_service"


@pytest.mark.unit
@pytest.mark.django_db
class TestControllerEventsView(APITestCase):
    """Tests for GET /api/v1/controller/events/ — tighter 3-day window."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.url = reverse("tasks:controller:controller-events")

    def test_missing_params_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_range_exceeding_3_days_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"since": VALID_SINCE, "until": OVER_3_DAYS_UNTIL})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "3 days" in str(response.data)

    def test_range_within_7_days_but_over_3_also_rejected(self):
        self.client.force_authenticate(user=self.user)
        # 6-day range — fine for other endpoints but rejected for events
        response = self.client.get(self.url, {"since": VALID_SINCE, "until": VALID_UNTIL_7})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_valid_3_day_range_returns_200(self):
        self.client.force_authenticate(user=self.user)
        mock_collector = _make_mock_collector()
        registry = _make_collectors_registry("main_jobevent_service", mock_collector)

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_HOURLY_PATCH, return_value=registry):
            response = self.client.get(self.url, {"since": VALID_SINCE, "until": VALID_UNTIL_3})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["collector_type"] == "main_jobevent_service"


@pytest.mark.unit
@pytest.mark.django_db
class TestControllerSnapshotView(APITestCase):
    """Tests for GET /api/v1/controller/snapshot/"""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.url = reverse("tasks:controller:controller-snapshot")

    def _make_snapshot_registry(self, collectors=None):
        """Build a snapshot registry where all collectors succeed."""
        if collectors is None:
            collectors = ["execution_environments", "controller_version_service", "table_metadata", "config"]

        def _make_func(collector_type):
            def collector_func(**kw):
                return _make_mock_collector(data={"type": collector_type})
            return collector_func

        return {c: {"collector_func": _make_func(c)} for c in collectors}

    def test_unauthenticated_returns_401_or_403(self):
        response = self.client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_awx_db_unavailable_returns_503(self):
        self.client.force_authenticate(user=self.user)
        with patch(_DB_PATCH, side_effect=Exception("no conn")):
            response = self.client.get(self.url)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_all_collectors_success_returns_200(self):
        self.client.force_authenticate(user=self.user)
        registry = self._make_snapshot_registry()

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_SNAPSHOT_PATCH, return_value=registry):
            response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert "collectors" in response.data
        assert "errors" in response.data
        assert "collected_at" in response.data
        assert response.data["errors"] == {}

    def test_partial_collector_failure_returns_200_with_errors(self):
        self.client.force_authenticate(user=self.user)
        failing_mock = MagicMock()
        failing_mock.gather.side_effect = Exception("DB error")

        registry = {
            "execution_environments": {"collector_func": lambda **kw: _make_mock_collector()},
            "controller_version_service": {"collector_func": lambda **kw: failing_mock},
            "table_metadata": {"collector_func": lambda **kw: _make_mock_collector()},
            "config": {"collector_func": lambda **kw: _make_mock_collector()},
        }

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_SNAPSHOT_PATCH, return_value=registry):
            response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert "controller_version_service" in response.data["errors"]
        assert "execution_environments" in response.data["collectors"]

    def test_unknown_collector_in_query_param_returns_error_entry(self):
        self.client.force_authenticate(user=self.user)
        registry = self._make_snapshot_registry(["execution_environments"])

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_SNAPSHOT_PATCH, return_value=registry):
            response = self.client.get(self.url, {"collectors": "execution_environments,nonexistent"})

        assert response.status_code == status.HTTP_200_OK
        assert "nonexistent" in response.data["errors"]

    def test_collectors_query_param_subsets_results(self):
        self.client.force_authenticate(user=self.user)
        registry = self._make_snapshot_registry()

        with patch(_DB_PATCH, return_value=MagicMock()), patch(_SNAPSHOT_PATCH, return_value=registry):
            response = self.client.get(self.url, {"collectors": "config"})

        assert response.status_code == status.HTTP_200_OK
        assert "config" in response.data["collectors"]
        assert "execution_environments" not in response.data["collectors"]
