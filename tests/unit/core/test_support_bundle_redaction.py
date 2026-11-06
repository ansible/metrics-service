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


@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        ("redis://:redispw@cache:6379/0", "redis://**REDACTED**@cache:6379/0"),
        ("postgres://:pgpw@db:5432/metrics", "postgres://**REDACTED**@db:5432/metrics"),
        ("amqp://:mqpw@broker:5672/vhost", "amqp://**REDACTED**@broker:5672/vhost"),
        ("postgresql://metrics_user:s3cr3t@db/x", "postgresql://**REDACTED**@db/x"),
        ("redis://cache:6379/0", "redis://cache:6379/0"),
    ],
)
def test_url_userinfo_is_redacted_for_every_userinfo_form(dsn, expected):
    """Password-only DSNs (``scheme://:pw@host``) must not survive redaction."""
    redacted, summary = redact_settings({"CACHE": {"LOCATION": dsn}})

    assert redacted["CACHE"]["LOCATION"] == expected
    for secret in ("redispw", "pgpw", "mqpw", "s3cr3t"):
        assert secret not in str(redacted)
    assert summary["redacted_key_count"] == (0 if expected == dsn else 1)


def test_authorization_header_values_are_redacted():
    data = {"header": "Bearer abc.def.ghi"}

    redacted, _ = redact_settings(data)

    assert redacted["header"] == "Bearer **REDACTED**"


def test_authorization_header_is_redacted_in_the_middle_of_a_string():
    data = {"detail": "request failed with Authorization: Bearer abc.def.ghi"}

    redacted, _ = redact_settings(data)

    assert redacted["detail"] == "request failed with Authorization: Bearer **REDACTED**"


@pytest.mark.parametrize(
    ("payload", "secret"),
    [
        ("failed to POST https://segment/api?token=abc123 (401)", "abc123"),
        ("curl --password=hunter2 --user=admin", "hunter2"),
        ("SEGMENT_WRITE_KEY=abc123", "abc123"),
        ("API_KEY = 'abc123'", "abc123"),
        ("databases:\n  default:\n    password: abc123", "abc123"),
        ("https://api.segment.io/v1/batch?access_token=abc123", "abc123"),
    ],
)
def test_secret_key_value_pairs_are_redacted_in_free_text(payload, secret):
    """Error messages carry ``?token=``/``--password=``/``KEY=`` shapes verbatim."""
    redacted, summary = redact_settings({"error_message": payload})

    assert secret not in str(redacted)
    assert redacted["error_message"] != payload
    assert summary["redacted_paths"] == ["error_message"]


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


@pytest.mark.parametrize(
    "key",
    [
        "redacted_key_count",
        "key_count",
        "api_key_count",
        "token_budget",
        "secret_scan_duration_ms",
        "password_policy",
        "applied_migrations_count",
        "task_timeout_seconds",
        "max_payload_bytes",
    ],
)
def test_counter_and_metadata_keys_are_not_redacted(key):
    """A count/policy/measurement is data, not a credential."""
    redacted, summary = redact_settings({key: 42})

    assert redacted == {key: 42}
    assert summary == {"redacted_key_count": 0, "redacted_paths": []}


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "auth_token",
        "db_password",
        "secret",
        "my_secret",
        "refresh_token",
        "root_password",
        "private_key",
        "client_secret",
        "SECRET_KEY",
        "SEGMENT_WRITE_KEY",
    ],
)
def test_credential_keys_are_still_redacted(key):
    """The counter/policy allow-list must not weaken genuine credential coverage."""
    redacted, summary = redact_settings({key: "super-secret-value"})

    assert redacted == {key: REDACTED}
    assert summary["redacted_key_count"] == 1
    assert summary["redacted_paths"] == [key]


@pytest.mark.parametrize("key", ["token_budget", "key_count", "password_policy"])
def test_credential_looking_values_are_redacted_even_under_metadata_keys(key):
    """The value-level pass is independent of the key-name allow-list."""
    dsn = "redis://:redispw@cache:6379/0"

    redacted, summary = redact_settings({key: dsn})

    assert redacted == {key: "redis://**REDACTED**@cache:6379/0"}
    assert summary["redacted_paths"] == [key]
