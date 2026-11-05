"""Recursive redaction for support-bundle output.

Key names matching :data:`SECRET_KEY_MARKERS` are replaced wholesale. Values that do
not sit under a suspicious key still get a value-level pass so that credentials
embedded in connection strings or ``Authorization``-style headers do not leak.

The marker list lives in code, not configuration, so it cannot be weakened per
environment by accident.
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
_URL_USERINFO_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)[^/\s:@]+(?::[^/\s@]*)?@")

#: ``Bearer <token>`` / ``Basic <token>`` / ``Token <token>`` header values.
_AUTHORIZATION_RE = re.compile(r"^(?P<scheme>Bearer|Basic|Token)\s+\S+$", re.IGNORECASE)


def is_secret_key(key: Any) -> bool:
    """Return True when *key* contains one of the secret markers."""
    if not isinstance(key, str):
        return False
    upper = key.upper()
    return any(marker in upper for marker in SECRET_KEY_MARKERS)


def redact_string(value: str) -> str:
    """Redact credentials embedded in a string, e.g. URL userinfo or auth headers."""
    value = _URL_USERINFO_RE.sub(rf"\g<scheme>{REDACTED}@", value)
    match = _AUTHORIZATION_RE.match(value)
    if match:
        return f"{match.group('scheme')} {REDACTED}"
    return value


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
