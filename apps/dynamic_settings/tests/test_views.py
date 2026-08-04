"""
Unit tests for the Settings API views.

Coverage:
    - Unauthenticated access is rejected
    - Non-admin access is rejected
    - Admin GET returns all settings grouped by category
    - Admin GET shows registry default for keys with no DB row
    - Admin GET returns null for sensitive settings
    - Admin GET exposes requires list and effective_value per entry
    - effective_value is False when a required parent flag is disabled
    - effective_value is True when all dependencies are satisfied
    - Admin PATCH updates a setting and returns the new value
    - Admin PATCH returns warnings when a required dependency is broken
    - Admin PATCH returns no warnings when all dependencies are satisfied
    - Admin PATCH rejects unknown keys
    - Admin PATCH rejects wrong types
    - Admin PATCH rejects sensitive settings
    - Admin PATCH with empty dict is rejected
    - After PATCH the Setting DB row carries the correct JSON value
"""

import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.dynamic_settings.models import Setting
from apps.dynamic_settings.registry import SETTINGS_REGISTRY, SettingDef


SETTINGS_URL = "/api/v1/settings/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_client(admin_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


def _anon_client() -> APIClient:
    return APIClient()


def _regular_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# Authentication / Permission tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
def test_unauthenticated_get_returns_403():
    """Unauthenticated request must be rejected."""
    response = _anon_client().get(SETTINGS_URL)
    assert response.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_non_admin_get_returns_403(user):
    """Regular (non-superuser) user must be rejected by IsSystemAdminOrAuditor."""
    response = _regular_client(user).get(SETTINGS_URL)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET — structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_get_returns_200(admin_user):
    """Admin GET /api/v1/settings/ returns HTTP 200."""
    response = _admin_client(admin_user).get(SETTINGS_URL)
    assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_get_has_expected_categories(admin_user):
    """Response groups settings under the categories defined in the registry."""
    response = _admin_client(admin_user).get(SETTINGS_URL)
    data = response.json()
    assert "collection" in data
    assert "dashboard" in data
    assert "anonymization" in data
    assert "advanced" in data


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_get_all_registry_keys_present(admin_user):
    """Every key in SETTINGS_REGISTRY appears in the correct category."""
    response = _admin_client(admin_user).get(SETTINGS_URL)
    data = response.json()

    for key, defn in SETTINGS_REGISTRY.items():
        assert defn.category in data, f"Category {defn.category!r} missing from response"
        assert key in data[defn.category], f"Key {key!r} missing from category {defn.category!r}"


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_get_no_db_row_shows_default(admin_user):
    """When no DB row exists for a key the response value equals the registry default."""
    # Ensure no DB row exists for INDIRECT_NODE_COLLECTION (default=False)
    Setting.objects.filter(setting_key="INDIRECT_NODE_COLLECTION").delete()

    response = _admin_client(admin_user).get(SETTINGS_URL)
    data = response.json()

    entry = data["advanced"]["INDIRECT_NODE_COLLECTION"]
    assert entry["value"] == SETTINGS_REGISTRY["INDIRECT_NODE_COLLECTION"].default
    assert entry["modified"] is None
    assert entry["modified_by"] is None


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_get_entry_shape(admin_user):
    """Each setting entry has the expected shape with all required fields."""
    response = _admin_client(admin_user).get(SETTINGS_URL)
    data = response.json()

    entry = data["collection"]["METRICS_COLLECTION"]
    for field in ("value", "effective_value", "default", "type", "label", "description", "requires", "modified", "modified_by"):
        assert field in entry, f"Field {field!r} missing from setting entry"


# ---------------------------------------------------------------------------
# PATCH — success paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_patch_boolean_key_returns_200(admin_user):
    """Admin PATCH with a known boolean key returns HTTP 200."""
    response = _admin_client(admin_user).patch(
        SETTINGS_URL,
        data={"METRICS_COLLECTION": False},
        format="json",
    )
    assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_patch_value_reflected_in_response(admin_user):
    """After PATCH the returned GET response shows the updated value."""
    client = _admin_client(admin_user)
    response = client.patch(
        SETTINGS_URL,
        data={"ANONYMIZED_DATA_COLLECTION": False},
        format="json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["anonymization"]["ANONYMIZED_DATA_COLLECTION"]["value"] is False


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_patch_writes_db_row(admin_user):
    """PATCH creates a Setting DB row with the correct JSON-serialised value."""
    Setting.objects.filter(setting_key="EVENTS_COLLECTION").delete()

    _admin_client(admin_user).patch(
        SETTINGS_URL,
        data={"EVENTS_COLLECTION": False},
        format="json",
    )

    row = Setting.objects.filter(setting_key="EVENTS_COLLECTION").first()
    assert row is not None
    assert json.loads(row.current_value) is False


# ---------------------------------------------------------------------------
# PATCH — error paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_patch_unknown_key_returns_400(admin_user):
    """PATCH with an unknown key returns HTTP 400."""
    response = _admin_client(admin_user).patch(
        SETTINGS_URL,
        data={"TOTALLY_UNKNOWN_FLAG": True},
        format="json",
    )
    assert response.status_code == 400
    assert "TOTALLY_UNKNOWN_FLAG" in response.json()


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_patch_wrong_type_returns_400(admin_user):
    """PATCH with a string value for a boolean setting returns HTTP 400."""
    response = _admin_client(admin_user).patch(
        SETTINGS_URL,
        data={"METRICS_COLLECTION": "yes"},
        format="json",
    )
    assert response.status_code == 400
    assert "METRICS_COLLECTION" in response.json()


@pytest.mark.unit
@pytest.mark.django_db
def test_admin_patch_empty_dict_returns_400(admin_user):
    """PATCH with an empty JSON object returns HTTP 400."""
    response = _admin_client(admin_user).patch(
        SETTINGS_URL,
        data={},
        format="json",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# effective_value and requires
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
def test_requires_list_present_on_dependent_flags(admin_user):
    """Flags with dependencies expose a non-empty requires list."""
    response = _admin_client(admin_user).get(SETTINGS_URL)
    data = response.json()
    # EVENTS_COLLECTION requires METRICS_COLLECTION
    assert data["collection"]["EVENTS_COLLECTION"]["requires"] == ["METRICS_COLLECTION"]
    # CORE_DASHBOARD_COLLECTION requires two flags
    assert set(data["dashboard"]["CORE_DASHBOARD_COLLECTION"]["requires"]) == {
        "UNIFIED_JOBS_COLLECTION",
        "JOB_HOST_SUMMARY_COLLECTION",
    }
    # METRICS_COLLECTION has no requirements
    assert data["collection"]["METRICS_COLLECTION"]["requires"] == []


@pytest.mark.unit
@pytest.mark.django_db
def test_effective_value_false_when_parent_disabled(admin_user):
    """effective_value is False for a flag when a required parent is disabled."""
    # Disable METRICS_COLLECTION — all collection sub-flags should be effectively off
    Setting.objects.filter(setting_key="METRICS_COLLECTION").delete()
    from apps.dynamic_settings.utils import log_setting_change

    log_setting_change(admin_user, "METRICS_COLLECTION", False, True)

    response = _admin_client(admin_user).get(SETTINGS_URL)
    data = response.json()

    # EVENTS_COLLECTION is still "on" (value=True) but effective_value must be False
    events = data["collection"]["EVENTS_COLLECTION"]
    assert events["value"] is True
    assert events["effective_value"] is False

    # CORE_DASHBOARD_COLLECTION transitively needs METRICS_COLLECTION → also False
    core = data["dashboard"]["CORE_DASHBOARD_COLLECTION"]
    assert core["effective_value"] is False


@pytest.mark.unit
@pytest.mark.django_db
def test_effective_value_true_when_all_deps_satisfied(admin_user):
    """effective_value equals value when all required flags are enabled."""
    response = _admin_client(admin_user).get(SETTINGS_URL)
    data = response.json()
    # Default state: all flags enabled — effective_value should match value
    for category in data.values():
        for key, entry in category.items():
            if entry["value"] is True and entry["effective_value"] is not None:
                assert entry["effective_value"] is True, (
                    f"{key}: value=True but effective_value={entry['effective_value']}"
                )


@pytest.mark.unit
@pytest.mark.django_db
def test_patch_returns_warnings_when_dependency_broken(admin_user):
    """PATCH that disables a required flag returns warnings for dependent enabled flags."""
    response = _admin_client(admin_user).patch(
        SETTINGS_URL,
        data={"METRICS_COLLECTION": False},
        format="json",
    )
    assert response.status_code == 200
    data = response.json()
    # warnings key present because EVENTS_COLLECTION, ANONYMIZED_DATA_COLLECTION, etc.
    # are still enabled but their required METRICS_COLLECTION is now off
    assert "warnings" in data
    assert any("METRICS_COLLECTION" in msg for msg in data["warnings"].values())


@pytest.mark.unit
@pytest.mark.django_db
def test_patch_no_warnings_when_deps_satisfied(admin_user):
    """PATCH that doesn't break any dependency returns no warnings key."""
    response = _admin_client(admin_user).patch(
        SETTINGS_URL,
        data={"INDIRECT_NODE_COLLECTION": True},
        format="json",
    )
    assert response.status_code == 200
    data = response.json()
    # INDIRECT_NODE_COLLECTION has no requires — no warnings expected
    assert "warnings" not in data or data["warnings"] == {}


# ---------------------------------------------------------------------------
# Sensitive setting masking
# ---------------------------------------------------------------------------

_SENSITIVE_REGISTRY = {
    **SETTINGS_REGISTRY,
    "SECRET_TOKEN": SettingDef(
        category="advanced",
        label="Secret Token",
        type="string",
        default="",
        sensitive=True,
        description="A sensitive credential — never echoed back.",
    ),
}


@pytest.mark.unit
@pytest.mark.django_db
def test_sensitive_setting_returns_null_in_get(admin_user):
    """GET returns null for any setting marked sensitive=True in the registry."""
    with patch("apps.dynamic_settings.v1.views.SETTINGS_REGISTRY", _SENSITIVE_REGISTRY):
        response = _admin_client(admin_user).get(SETTINGS_URL)
    data = response.json()
    assert response.status_code == 200
    entry = data["advanced"]["SECRET_TOKEN"]
    assert entry["value"] is None


@pytest.mark.unit
@pytest.mark.django_db
def test_sensitive_setting_patch_returns_400(admin_user):
    """PATCH of a sensitive setting returns 400 — values cannot be set via the API."""
    with patch("apps.dynamic_settings.v1.views.SETTINGS_REGISTRY", _SENSITIVE_REGISTRY):
        response = _admin_client(admin_user).patch(
            SETTINGS_URL,
            data={"SECRET_TOKEN": "my-secret"},
            format="json",
        )
    assert response.status_code == 400
    assert "SECRET_TOKEN" in response.json()
