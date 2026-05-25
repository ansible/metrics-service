"""
Tests for apps/bi_connector/v1/mixins.py
"""

import json
from unittest.mock import patch

import pytest

from apps.bi_connector.v1.mixins import BiConnectorThrottle, is_bi_collector_enabled
from apps.dynamic_settings.models import Setting


@pytest.mark.unit
@pytest.mark.django_db
class TestIsBiCollectorEnabled:
    """Tests for the is_bi_collector_enabled() helper function."""

    def test_returns_true_from_db_setting(self):
        Setting.objects.create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            current_value=json.dumps({"main_host": True}),
        )
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is True

    def test_returns_false_from_db_setting(self):
        Setting.objects.create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            current_value=json.dumps({"main_host": False}),
        )
        result = is_bi_collector_enabled("main_host", default=True)
        assert result is False

    def test_returns_default_true_when_no_setting(self):
        result = is_bi_collector_enabled("main_host", default=True)
        assert result is True

    def test_returns_default_false_when_no_setting(self):
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_falls_back_to_default_when_collector_not_in_setting(self):
        Setting.objects.create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            current_value=json.dumps({"other_collector": True}),
        )
        # "main_host" not in the setting → fall back to default
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_falls_back_to_default_true_when_collector_not_in_setting(self):
        Setting.objects.create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            current_value=json.dumps({"other_collector": True}),
        )
        result = is_bi_collector_enabled("main_host", default=True)
        assert result is True

    def test_handles_corrupted_json_gracefully_returns_default(self):
        Setting.objects.create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            current_value="not valid json }{",
        )
        result = is_bi_collector_enabled("main_host", default=True)
        assert result is True

    def test_handles_corrupted_json_returns_default_false(self):
        Setting.objects.create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            current_value="not valid json }{",
        )
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_returns_default_on_exception(self):
        _setting_patch = "apps.bi_connector.v1.mixins.Setting"
        with patch(_setting_patch) as mock_setting_cls:
            mock_setting_cls.objects.filter.side_effect = RuntimeError("DB down")
            result = is_bi_collector_enabled("main_host", default=True)
        assert result is True

    def test_returns_default_false_on_exception(self):
        _setting_patch = "apps.bi_connector.v1.mixins.Setting"
        with patch(_setting_patch) as mock_setting_cls:
            mock_setting_cls.objects.filter.side_effect = RuntimeError("DB down")
            result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_setting_with_non_dict_value_falls_back_to_default(self):
        # If current_value is a JSON array, not a dict
        Setting.objects.create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            current_value=json.dumps(["main_host"]),
        )
        result = is_bi_collector_enabled("main_host", default=False)
        assert result is False

    def test_multiple_collectors_returns_correct_value(self):
        Setting.objects.create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            current_value=json.dumps({
                "main_host": True,
                "unified_jobs": False,
                "config": True,
            }),
        )
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
