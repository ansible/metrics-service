"""Helpers for translating canonical API URLs to the configured public root."""

from urllib.parse import urlsplit, urlunsplit


def replace_api_root(url: str, public_api_root: str | None) -> str:
    """Replace the internal ``/api`` root while preserving its remaining path.

    The application URLconf uses paths such as ``/api/v1/tasks/``. With the
    public root ``/api/metrics/``, this returns ``/api/metrics/v1/tasks/``:
    only the leading ``/api`` is replaced; the ``/v1/tasks/`` suffix remains.
    Already-prefixed URLs are left unchanged.
    """
    if not public_api_root:
        return url

    public_api_root = "/" + "/".join(part for part in public_api_root.split("/") if part)
    if public_api_root == "/":
        return url

    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    path = parts.path
    if path == public_api_root or path.startswith(public_api_root + "/"):
        return url
    if path != "/api" and not path.startswith("/api/"):
        return url

    return urlunsplit(parts._replace(path=public_api_root + path[len("/api") :]))
