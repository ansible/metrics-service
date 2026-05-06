"""Segment analytics key loading utilities.

This module provides functions to load the SEGMENT_WRITE_KEY from a file
in the production environment. The key file is typically installed by
the pipeline at /etc/ansible-automation-platform/metrics/segment-write-key.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def read_segment_key_from_path(path: Path) -> str | None:
    """Read SEGMENT_WRITE_KEY from a single file. Returns the key or None.

    Pipeline passes build secret metrics-service-segment-write-keys (SEGMENT_WRITE_KEY_DEV for
    PR/devel, SEGMENT_WRITE_KEY_PROD for GA); one key is installed into that path.
    File content is the raw plaintext key (no encoding).

    Args:
        path: Path to the segment write key file

    Returns:
        The segment write key as a string, or None if the file doesn't exist or is empty
    """
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
    """Load SEGMENT_WRITE_KEY from file and set on Dynaconf.

    Used at module load and in tests. Respects environment variable and settings
    precedence: does not overwrite if already set.

    Args:
        path: Path to the segment write key file. If None, uses METRICS_SERVICE_SEGMENT_WRITE_KEY_FILE
              environment variable or defaults to /etc/ansible-automation-platform/metrics/segment-write-key
        dynaconf_instance: The Dynaconf instance to set the key on. If None, no action is taken
                          (caller should pass the instance from their settings context)
    """
    if path is None:
        _segment_write_key_path = os.environ.get(
            "METRICS_SERVICE_SEGMENT_WRITE_KEY_FILE",
            "/etc/ansible-automation-platform/metrics/segment-write-key",
        )
        path = Path(_segment_write_key_path)

    if dynaconf_instance is None:
        return

    # Respect env/settings precedence: do not overwrite if already set
    if os.environ.get("METRICS_SERVICE_SEGMENT_WRITE_KEY", "").strip():
        return
    if dynaconf_instance.get("SEGMENT_WRITE_KEY"):
        return
    if not path.exists():
        return

    key = read_segment_key_from_path(path)
    if key:
        dynaconf_instance.set("SEGMENT_WRITE_KEY", key)
