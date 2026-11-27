"""
Utility functions for dynamic settings management.

This module provides functions for removing and initializing default settings.
"""

import json
import logging

from .models import Setting

logger = logging.getLogger(__name__)


# uv run ./manage.py metrics_service remove-default-settings [--all-settings]
def remove_default_settings(all_settings: bool = False, **_kwargs) -> int:
    """
    Remove settings from the database.

    With all_settings=True removes every row. Without it this is a no-op —
    there are no longer any known-default keys to target individually.
    The **_kwargs absorbs legacy all_known= callers without raising.
    """
    if not all_settings:
        logger.debug("No settings found to remove")
        return 0

    deleted_count, _ = Setting.objects.all().delete()
    if deleted_count > 0:
        logger.info(f"Removed {deleted_count} settings from database")
    return deleted_count


# uv run ./manage.py metrics_service init-default-settings
def initialize_default_settings(**_kwargs) -> None:
    """
    Upgrade hook for FEATURE flag DB rows.

    No flags are pre-seeded into the database. Feature flags resolve at runtime
    from the ``settings.FEATURE`` dict (env var overrides via
    ``METRICS_SERVICE_FEATURE__*`` merge in via dynaconf) with ``false`` DB rows
    as explicit opt-outs.

    On each call, any ``true`` DB row for a FEATURE flag key is deleted — a
    ``true`` row is redundant (the static default and env var both produce
    ``true`` when no row exists) and blocks env var overrides.  ``false`` rows
    are kept: they represent an explicit opt-out that must survive upgrades.

    The **_kwargs absorbs legacy overwrite= callers without raising.
    """
    from django.conf import settings as django_settings

    feature_dict = getattr(django_settings, "FEATURE", {})
    cleaned_count = 0
    for flag_key in feature_dict:
        try:
            deleted, _ = Setting.objects.filter(
                setting_key=flag_key,
                current_value=json.dumps(True),
            ).delete()
            if deleted:
                logger.info(f"Removed redundant 'true' row for '{flag_key}'; env var now applies")
                cleaned_count += deleted
        except Exception as e:
            logger.warning(f"Failed to clean up feature flag row for '{flag_key}': {e}")
    if cleaned_count > 0:
        logger.info(f"Cleaned up {cleaned_count} redundant feature flag row(s)")
