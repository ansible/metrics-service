"""Segment integration utilities."""

import logging
import os
from pathlib import Path


def read_segment_key_from_path(path: Path) -> str | None:
    """Read SEGMENT_WRITE_KEY from a single file. Returns the key or None."""
    logger = logging.getLogger(__name__)
    try:
        if not path.is_file():
            return None
        key = path.read_text().strip()
        return key if key else None
    except OSError as e:
        filename = getattr(e, "filename", path)
        logger.error(
            "Failed to read segment write key from %s: %s",
            filename,
            e,
            exc_info=True,
        )
        return None


def load_segment_write_key_from_file(
    path: Path | None = None,
    dynaconf_instance=None,
) -> None:
    """Load SEGMENT_WRITE_KEY from file and set on Dynaconf. Used at module load and in tests."""
    if path is None:
        _segment_write_key_path = os.environ.get(
            "METRICS_SERVICE_SEGMENT_WRITE_KEY_FILE",
            "/etc/ansible-automation-platform/metrics/segment-write-key",
        )
        path = Path(_segment_write_key_path)
    if dynaconf_instance is None:
        dynaconf_instance = None
    # Respect env/settings precedence: do not overwrite if already set
    if os.environ.get("METRICS_SERVICE_SEGMENT_WRITE_KEY", "").strip():
        return
    if dynaconf_instance and dynaconf_instance.get("SEGMENT_WRITE_KEY"):
        return
    if not path.exists():
        return
    key = read_segment_key_from_path(path)
    if key and dynaconf_instance:
        dynaconf_instance.set("SEGMENT_WRITE_KEY", key)
