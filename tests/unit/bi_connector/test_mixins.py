"""
Tests for apps/bi_connector/v1/mixins.py
"""

import json
from unittest.mock import patch

import pytest

from apps.bi_connector.v1.mixins import BiConnectorThrottle, is_bi_collector_enabled
from apps.dynamic_settings.models import Setting

_SETTING_PATCH = "apps.dynamic_settings.models.Setting"


@pytest.mark.unit
@pytest.mark.django_db
class TestIsBiCollectorEnabled:
    """Tests for the is_bi_collector_enabled() helper function."""

    def setup_method(self):
        # Remove auto-seeded BI_CONNECTOR_COLLECTORS so each test starts clean
        Setting.objects.filter(setting_key="BI_CONNECTOR_COLLECTORS").delete()

    def _set_collectors(self, value: dict | str):
        """Helper: write/overwrite the BI_CONNECTOR_COLLECTORS setting."""
        raw = value if isinstance(value, str) else json.dumps(value)
        Setting.objects.update_or_create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            defaults={"current_value": raw},
        )

    def test_returns_true_from_db_setting(self):
        self._set_collectors({"main_host": True})
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is True

    def test_returns_false_from_db_setting(self):
        self._set_collectors({"main_host": False})
        result = is_bi_collector_enabled("main_host", default=True)
        assert result is False

    def test_returns_default_true_when_no_setting(self):
        result = is_bi_collector_enabled("main_host", default=True)
        assert result is True

    def test_returns_default_false_when_no_setting(self):
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_falls_back_to_default_when_collector_not_in_setting(self):
        self._set_collectors({"other_collector": True})
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_falls_back_to_default_true_when_collector_not_in_setting(self):
        self._set_collectors({"other_collector": True})
        result = is_bi_collector_enabled("main_host", default=True)
        assert result is True

    def test_handles_corrupted_json_gracefully_returns_default(self):
        self._set_collectors("not valid json }{")
        result = is_bi_collector_enabled("main_host", default=True)
        assert result is True

    def test_handles_corrupted_json_returns_default_false(self):
        self._set_collectors("not valid json }{")
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_returns_default_on_exception(self):
        with patch(_SETTING_PATCH) as mock_setting_cls:
            mock_setting_cls.objects.filter.side_effect = RuntimeError("DB down")
            result = is_bi_collector_enabled("main_host", default=True)
        assert result is True

    def test_returns_default_false_on_exception(self):
        with patch(_SETTING_PATCH) as mock_setting_cls:
            mock_setting_cls.objects.filter.side_effect = RuntimeError("DB down")
            result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_setting_with_non_dict_value_falls_back_to_default(self):
        self._set_collectors(["main_host"])  # JSON array, not dict
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_multiple_collectors_returns_correct_value(self):
        self._set_collectors({"main_host": True, "unified_jobs": False, "config": True})
        assert is_bi_collector_enabled("main_host") is True
        assert is_bi_collector_enabled("unified_jobs") is False
        assert is_bi_collector_enabled("config") is True

    def test_default_parameter_defaults_to_true(self):
        # When called with no default kwarg, missing key should return True
        result = is_bi_collector_enabled("nonexistent_collector")
        assert result is True


@pytest.mark.unit
class TestBiConnectorThrottle:
    """Tests for the BiConnectorThrottle class."""

    def test_scope_is_bi_connector(self):
        assert BiConnectorThrottle.scope == "bi_connector"

    def test_get_rate_returns_default_when_not_configured(self):
        from django.core.exceptions import ImproperlyConfigured

        throttle = BiConnectorThrottle()
        with patch.object(
            throttle.__class__.__bases__[0],
            "get_rate",
            side_effect=ImproperlyConfigured("throttle rate not set"),
        ):
            rate = throttle.get_rate()
        assert rate == "30/hour"

    def test_get_rate_returns_configured_rate(self):
        throttle = BiConnectorThrottle()
        with patch.object(
            throttle.__class__.__bases__[0],
            "get_rate",
            return_value="60/hour",
        ):
            rate = throttle.get_rate()
        assert rate == "60/hour"
