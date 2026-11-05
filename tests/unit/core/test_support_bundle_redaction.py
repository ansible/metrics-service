"""Unit tests for support-bundle redaction."""

import pytest

from apps.core.support_bundle.redaction import REDACTED, redact_settings, redact_value

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "key",
    [
        "SECRET_KEY",
        "DATABASES__default__PASSWORD",
        "RESOURCE_SERVER__SECRET_KEY",
        "SEGMENT_WRITE_KEY",
        "AUTH_TOKEN",
        "CLIENT_CREDENTIAL",
        "PRIVATE_DATA",
    ],
)
def test_secret_keys_are_redacted(key):
    redacted, summary = redact_settings({key: "super-secret-value"})

    assert redacted[key] == REDACTED
    assert "super-secret-value" not in str(redacted)
    assert summary["redacted_key_count"] == 1
    assert summary["redacted_paths"] == [key]


def test_nested_dicts_and_lists_are_redacted_recursively():
    data = {
        "DATABASES": {
            "default": {"NAME": "metrics_service", "PASSWORD": "db-password"},
        },
        "FEATURES": [{"name": "segment", "TOKEN": "segment-token"}],
    }

    redacted, summary = redact_settings(data)

    assert redacted["DATABASES"]["default"]["PASSWORD"] == REDACTED
    assert redacted["DATABASES"]["default"]["NAME"] == "metrics_service"
    assert redacted["FEATURES"][0]["TOKEN"] == REDACTED
    assert "db-password" not in str(redacted)
    assert "segment-token" not in str(redacted)
    assert "DATABASES.default.PASSWORD" in summary["redacted_paths"]
    assert "FEATURES[0].TOKEN" in summary["redacted_paths"]


def test_non_secret_keys_are_preserved():
    data = {"TASK_TIMEOUT": 3600, "INSTALL_TYPE": "operator", "DEBUG": False}

    redacted, summary = redact_settings(data)

    assert redacted == data
    assert summary == {"redacted_key_count": 0, "redacted_paths": []}


def test_url_userinfo_is_redacted_under_innocuous_key():
    data = {"BROKER_URL": "postgresql://metrics_user:s3cr3t@db.example.com:5432/metrics"}

    redacted, summary = redact_settings(data)

    assert redacted["BROKER_URL"] == "postgresql://**REDACTED**@db.example.com:5432/metrics"
    assert "s3cr3t" not in str(redacted)
    assert summary["redacted_paths"] == ["BROKER_URL"]


def test_authorization_header_values_are_redacted():
    data = {"header": "Bearer abc.def.ghi"}

    redacted, _ = redact_settings(data)

    assert redacted["header"] == "Bearer **REDACTED**"


def test_redaction_summary_contains_paths_but_no_values():
    secret = "do-not-leak-this"
    _, summary = redact_settings({"APP": {"SECRET_KEY": secret, "API_TOKEN": "also-secret"}})

    serialized = str(summary)
    assert secret not in serialized
    assert "also-secret" not in serialized
    assert "APP.SECRET_KEY" in summary["redacted_paths"]
    assert "APP.API_TOKEN" in summary["redacted_paths"]


def test_redact_value_is_recursive_and_non_mutating():
    original = {"TOKEN": "abc", "nested": [{"PASSWORD": "def"}]}

    redacted = redact_value(original)

    assert original == {"TOKEN": "abc", "nested": [{"PASSWORD": "def"}]}
    assert redacted == {"TOKEN": REDACTED, "nested": [{"PASSWORD": REDACTED}]}
