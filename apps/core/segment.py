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
    logger = logging.getLogger(__name__)
    import sys
    print(f"[SEGMENT] load_segment_write_key_from_file called", file=sys.stderr)
    print(f"[SEGMENT]   path={path}, dynaconf_instance={dynaconf_instance is not None}", file=sys.stderr)

    if path is None:
        _segment_write_key_path = os.environ.get(
            "METRICS_SERVICE_SEGMENT_WRITE_KEY_FILE",
            "/etc/ansible-automation-platform/metrics/segment-write-key",
        )
        path = Path(_segment_write_key_path)
        print(f"[SEGMENT]   resolved path={path}", file=sys.stderr)

    # Respect env/settings precedence: do not overwrite if already set
    env_key = os.environ.get("METRICS_SERVICE_SEGMENT_WRITE_KEY", "").strip()
    if env_key:
        print(f"[SEGMENT]   SEGMENT_WRITE_KEY already in env, skipping", file=sys.stderr)
        logger.debug("SEGMENT_WRITE_KEY already set in environment, skipping file load")
        return

    if dynaconf_instance is not None:
        existing_key = dynaconf_instance.get("SEGMENT_WRITE_KEY")
        print(f"[SEGMENT]   existing key in settings: {existing_key is not None}", file=sys.stderr)
        if existing_key:
            logger.debug("SEGMENT_WRITE_KEY already set in settings, skipping file load")
            return

    if not path.exists():
        print(f"[SEGMENT]   file does not exist: {path}", file=sys.stderr)
        logger.debug(f"Segment key file does not exist: {path}")
        return

    print(f"[SEGMENT]   reading key from file...", file=sys.stderr)
    key = read_segment_key_from_path(path)
    print(f"[SEGMENT]   key read: {key is not None and len(key) > 0}", file=sys.stderr)

    if key and dynaconf_instance is not None:
        print(f"[SEGMENT]   setting key in dynaconf", file=sys.stderr)
        logger.debug(f"Setting SEGMENT_WRITE_KEY from file: {path}")
        dynaconf_instance.set("SEGMENT_WRITE_KEY", key)
    elif not key:
        print(f"[SEGMENT]   WARNING: failed to read key", file=sys.stderr)
        logger.warning(f"Failed to read segment key from: {path}")
    elif dynaconf_instance is None:
        print(f"[SEGMENT]   WARNING: dynaconf_instance is None", file=sys.stderr)
        logger.warning("Cannot set SEGMENT_WRITE_KEY: dynaconf_instance is None")
