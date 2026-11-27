"""Helpers for translating canonical API URLs to the configured public root."""

from urllib.parse import urlsplit, urlunsplit


def resolve_service_prefixes(url_prefix: str | None, root_urlconf: str) -> tuple[str, str]:
    """Return the public API prefix and the bare service prefix.

    ``url_prefix`` is the full API prefix (e.g. ``"/api/metrics"``). When it is not
    set, both prefixes are derived from the first segment of ``root_urlconf``
    (e.g. ``"metrics_service"`` → ``"/metrics-service"``).
    """
    prefix = (url_prefix or "").strip().rstrip("/")
    if prefix:
        service_prefix = prefix[4:] if prefix.startswith("/api/") else prefix
        return prefix, service_prefix

    service_name = root_urlconf.split(".")[0].replace("_", "-")
    service_prefix = f"/{service_name}"
    return f"/api{service_prefix}", service_prefix


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
