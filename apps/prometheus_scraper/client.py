"""
Prometheus scrape client.

Handles WIT token acquisition from the gateway and HTTP scraping of
downstream Prometheus endpoints. Tokens are cached per target service
and refreshed before expiry.
"""

import logging
from datetime import UTC, datetime

import jwt as pyjwt
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_SCRAPER_CONFIG_KEY = "PROMETHEUS_SCRAPER"
_WIT_SCOPE = "aap_metrics_collection"
_WIT_AUDIENCE = "ansible-services"
_JWT_HEADER = "X-DAB-JW-TOKEN"


def _scraper_config() -> dict:
    return getattr(settings, _SCRAPER_CONFIG_KEY, {})


def _is_token_expiring(token: str, buffer_seconds: int) -> bool:
    """Return True if the token will expire within buffer_seconds."""
    try:
        decoded = pyjwt.decode(token, options={"verify_signature": False})
        exp = datetime.fromtimestamp(decoded["exp"], tz=UTC)
        remaining = (exp - datetime.now(tz=UTC)).total_seconds()
        return remaining < buffer_seconds
    except Exception:
        return True


class PrometheusScrapeClient:
    """
    Fetches WIT tokens from the gateway and scrapes Prometheus endpoints.

    One token is maintained per target service. Tokens are refreshed
    proactively when they are within TOKEN_REFRESH_BUFFER_SECONDS of expiry.

    Usage::

        client = PrometheusScrapeClient()
        results = client.scrape_all()
        # results = {"controller": {"status": "ok", "text": "..."}, ...}
    """

    def __init__(self):
        self._token_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _get_wit_client(self):
        """
        Return a configured WorkloadIdentityClient, or None if RESOURCE_SERVER
        is not set (e.g. local development without a gateway).
        """
        try:
            from ansible_base.resource_registry.workload_identity_client import get_workload_identity_client

            resource_server = getattr(settings, "RESOURCE_SERVER", {})
            if not resource_server.get("URL") or not resource_server.get("SECRET_KEY"):
                logger.warning(
                    "RESOURCE_SERVER URL/SECRET_KEY not configured — "
                    "cannot fetch WIT tokens. Set METRICS_SERVICE_RESOURCE_SERVER__URL "
                    "and METRICS_SERVICE_RESOURCE_SERVER__SECRET_KEY."
                )
                return None
            return get_workload_identity_client()
        except ImportError:
            logger.error("ansible_base not available; cannot fetch WIT tokens")
            return None

    def get_token(self, target_service: str) -> str | None:
        """
        Return a valid JWT for target_service, refreshing from the gateway if needed.
        """
        config = _scraper_config()
        buffer = config.get("TOKEN_REFRESH_BUFFER_SECONDS", 60)

        cached = self._token_cache.get(target_service)
        if cached and not _is_token_expiring(cached, buffer):
            return cached

        client = self._get_wit_client()
        if client is None:
            return None

        try:
            response = client.request_workload_jwt(
                scope=_WIT_SCOPE,
                audience=_WIT_AUDIENCE,
                claims={"aap_metrics_target_service": target_service},
            )
            self._token_cache[target_service] = response.jwt
            logger.debug("Refreshed WIT token for target_service=%s", target_service)
            return response.jwt
        except Exception as exc:
            logger.error("Failed to fetch WIT token for target_service=%s: %s", target_service, exc)
            return None

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def scrape(self, target: dict) -> dict:
        """
        Scrape a single Prometheus target.

        Args:
            target: Dict with keys ``service`` and ``url``.

        Returns:
            Dict with keys: ``service``, ``url``, ``status`` ("ok" | "error"),
            ``text`` (raw metrics text or None), ``error`` (message or None),
            ``http_status`` (int or None).
        """
        service = target["service"]
        url = target["url"]
        config = _scraper_config()
        timeout = config.get("SCRAPE_TIMEOUT_SECONDS", 30)
        verify = config.get("VERIFY_TLS", True)

        result = {"service": service, "url": url, "status": "error", "text": None, "error": None, "http_status": None}

        token = self.get_token(service)
        if token is None:
            result["error"] = "No WIT token available — check RESOURCE_SERVER configuration"
            logger.warning("Skipping scrape of %s: no token", url)
            return result

        try:
            resp = requests.get(url, headers={_JWT_HEADER: token}, timeout=timeout, verify=verify)
            result["http_status"] = resp.status_code
            if resp.ok:
                result["status"] = "ok"
                result["text"] = resp.text
                logger.info("Scraped %s: %d bytes", url, len(resp.text))
            else:
                result["error"] = f"HTTP {resp.status_code}"
                logger.warning("Scrape of %s returned HTTP %d", url, resp.status_code)
        except requests.exceptions.Timeout:
            result["error"] = f"Request timed out after {timeout}s"
            logger.error("Scrape of %s timed out", url)
        except requests.exceptions.RequestException as exc:
            result["error"] = str(exc)
            logger.error("Scrape of %s failed: %s", url, exc)

        return result

    def scrape_all(self, target_services: list[str] | None = None) -> dict[str, dict]:
        """
        Scrape all configured targets (or a specific subset).

        Args:
            target_services: Optional list of service names to restrict scraping.
                             If None, all configured targets are scraped.

        Returns:
            Dict mapping service name to its scrape result dict.
        """
        config = _scraper_config()
        targets = config.get("TARGETS", [])

        if target_services:
            targets = [t for t in targets if t["service"] in target_services]

        if not targets:
            logger.warning("No Prometheus scrape targets configured or matched")
            return {}

        results = {}
        for target in targets:
            results[target["service"]] = self.scrape(target)

        ok_count = sum(1 for r in results.values() if r["status"] == "ok")
        logger.info("Prometheus scrape complete: %d/%d targets succeeded", ok_count, len(results))
        return results
