"""Recursive redaction for support-bundle output.

Key names matching :data:`SECRET_KEY_MARKERS` are replaced wholesale. Values that do
not sit under a suspicious key still get a value-level pass so that credentials
embedded in connection strings, ``Authorization``-style headers, and ``key=value``
pairs in free-text error messages do not leak.

The marker list lives in code, not configuration, so it cannot be weakened per
environment by accident. The value-level pass is deliberately over-eager: a
false positive costs a redacted diagnostic string, a false negative leaks a
secret into a ticket attachment.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "**REDACTED**"

#: Case-insensitive substrings that mark a key as secret. ``KEY`` intentionally
#: covers ``SEGMENT_WRITE_KEY`` and other ``*_KEY`` settings.
SECRET_KEY_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "KEY",
    "CREDENTIAL",
    "AUTH",
    "PRIVATE",
    "SEGMENT_WRITE_KEY",
)

#: ``scheme://user:password@host`` -- replace the whole userinfo component.
#: Both the user and the password are optional so the common password-only forms
#: (``redis://:pw@host``, ``amqp://:pw@host/vhost``) are covered too.
_URL_USERINFO_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)[^\s/@]*(?::[^\s/@]*)?@")

#: ``Bearer <token>`` / ``Basic <token>`` / ``Token <token>`` anywhere in a string,
#: not only as the whole value, so ``Authorization: Bearer abc`` is covered.
_AUTHORIZATION_RE = re.compile(r"(?P<scheme>\bBearer|\bBasic|\bToken)\s+\S+", re.IGNORECASE)

#: ``password=hunter2`` / ``token: abc123`` / ``SEGMENT_WRITE_KEY=abc`` style pairs.
#: Strips the value of any ``key=value`` / ``key: value`` pair whose key looks
#: secret, in free text as well as in structured data.
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<prefix>(?<![A-Za-z0-9_.\-])[A-Za-z0-9_.\-]*"
    r"(?:PASSWORD|PASSWD|SECRET|TOKEN|API[_-]?KEY|[_-]KEY|CREDENTIAL|PRIVATE[_-]?KEY|AUTH)"
    r"[A-Za-z0-9_.\-]*\s*[=:]\s*)"
    # Never consume a bare ``Bearer``/``Basic``/``Token`` keyword: the
    # authorization pass above has already replaced the credential itself.
    r"(?P<value>(?!(?:Bearer|Basic|Token)\b)(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s,;&)\]}]+))",
    re.IGNORECASE,
)


def is_secret_key(key: Any) -> bool:
    """Return True when *key* contains one of the secret markers."""
    if not isinstance(key, str):
        return False
    upper = key.upper()
    return any(marker in upper for marker in SECRET_KEY_MARKERS)


def redact_string(value: str) -> str:
    """Redact credentials embedded in a string, e.g. URL userinfo or auth headers."""
    value = _URL_USERINFO_RE.sub(rf"\g<scheme>{REDACTED}@", value)
    value = _AUTHORIZATION_RE.sub(rf"\g<scheme> {REDACTED}", value)
    return _SECRET_ASSIGNMENT_RE.sub(rf"\g<prefix>{REDACTED}", value)


def redact_value(value: Any, path: str = "", redacted_paths: list[str] | None = None) -> Any:
    """Return a recursively redacted copy of *value*.

    Every redacted key or value appends its dotted path to *redacted_paths*; paths
    never contain the secret value itself.
    """
    if redacted_paths is None:
        redacted_paths = []

    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if is_secret_key(key):
                redacted_paths.append(child_path)
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_value(item, child_path, redacted_paths)
        return redacted

    if isinstance(value, (list, tuple)):
        return [redact_value(item, f"{path}[{index}]", redacted_paths) for index, item in enumerate(value)]

    if isinstance(value, str):
        redacted_string = redact_string(value)
        if redacted_string != value and path:
            redacted_paths.append(path)
        return redacted_string

    return value


def redact_settings(data: dict) -> tuple[dict, dict]:
    """Redact *data* and return ``(redacted_data, redaction_summary)``.

    The summary reports how many fields were redacted and their key paths only --
    never the values -- so it is safe to include in the bundle.
    """
    redacted_paths: list[str] = []
    redacted = redact_value(data, "", redacted_paths)
    summary = {
        "redacted_key_count": len(redacted_paths),
        "redacted_paths": sorted(redacted_paths),
    }
    return redacted, summary
