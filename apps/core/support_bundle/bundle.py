"""Assemble, describe, and write a support-bundle tarball."""

from __future__ import annotations

import io
import json
import os
import tarfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.core.support_bundle.collectors import (
    collect_ingestion,
    collect_meta,
    collect_queues,
    collect_schema,
    collect_settings,
    collect_tasks,
)
from apps.core.support_bundle.redaction import redact_value

BUNDLE_PREFIX = "support-bundle"

#: Section filename -> collector. This mapping is the single source of truth for
#: both the tarball contents and the dry-run manifest.
COLLECTORS = {
    "tasks.json": collect_tasks,
    "ingestion.json": collect_ingestion,
    "queues.json": collect_queues,
    "schema.json": collect_schema,
    "settings.json": collect_settings,
}

#: How many ``-2``/``-3`` suffixed names to try before giving up on a same-second
#: collision. ``O_EXCL`` guarantees we never overwrite an existing file.
MAX_NAME_ATTEMPTS = 100


class SupportBundleError(RuntimeError):
    """Raised when a support bundle cannot be written.

    A plain ``RuntimeError`` subclass keeps :mod:`apps.core.support_bundle`
    importable without Django management machinery; the management command
    translates it into a ``CommandError``.
    """


@dataclass(frozen=True)
class BundleResult:
    """Location and shape of a written support bundle."""

    path: Path
    bundle_name: str
    sections: tuple[str, ...]
    size_bytes: int


def build_bundle() -> dict[str, Any]:
    """Run every collector and return an ordered ``{filename: data}`` mapping.

    Every section -- not just ``settings.json`` -- is passed through
    :func:`redact_value` before it leaves this function. Collectors embed
    free-text error messages and raw dispatcherd replies (task arguments), both
    of which can carry credentials.
    """
    meta = collect_meta()
    sections: dict[str, Any] = {filename: collector() for filename, collector in COLLECTORS.items()}
    for section in sections.values():
        if isinstance(section, dict):
            section.setdefault("meta", meta)
    return {filename: redact_value(section) for filename, section in sections.items()}


def _record_count(value: Any) -> int:
    if isinstance(value, (dict, list, tuple)):
        return len(value)
    return 1


def _serialize(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=str).encode()


def manifest(sections: dict[str, Any] | None = None) -> list[dict]:
    """Describe what the bundle would contain without writing anything."""
    sections = build_bundle() if sections is None else sections
    return [
        {"name": filename, "records": _record_count(value), "bytes": len(_serialize(value))}
        for filename, value in sections.items()
    ]


def _validate_output_dir(output_dir: Path) -> None:
    if not output_dir.exists():
        raise SupportBundleError(f"Output directory does not exist: {output_dir}")
    if not output_dir.is_dir():
        raise SupportBundleError(f"Output directory is not a directory: {output_dir}")


def _create_bundle_file(output_dir: Path, bundle_name: str) -> tuple[Path, int]:
    """Create a new ``0600`` bundle file without following symlinks.

    ``O_CREAT | O_EXCL`` refuses to reuse an existing path (including a
    pre-planted symlink), ``O_NOFOLLOW`` blocks the symlink case explicitly on
    platforms that support it, and the file is created under the caller's
    directory only. A same-second collision gets a ``-2``/``-3`` suffix instead
    of silently overwriting the previous bundle.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for attempt in range(1, MAX_NAME_ATTEMPTS + 1):
        suffix = "" if attempt == 1 else f"-{attempt}"
        path = output_dir / f"{bundle_name}{suffix}.tar.gz"
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError as exc:
            if path.is_symlink():
                raise SupportBundleError(f"Refusing to write through a symlink: {path}") from exc
            continue
        except OSError as exc:
            raise SupportBundleError(f"Cannot create bundle file {path}: {exc}") from exc
        os.fchmod(descriptor, 0o600)
        return path, descriptor
    raise SupportBundleError(f"Could not find a free bundle filename for {bundle_name} in {output_dir}")


def write_tarball(output_dir: str | Path, sections: dict[str, Any] | None = None) -> BundleResult:
    """Write *sections* as ``<output_dir>/support-bundle-YYYYMMDD-HHMMSS.tar.gz``.

    The tarball is streamed straight to a fresh ``0600`` file: nothing is
    buffered in memory and no existing path is ever overwritten.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    _validate_output_dir(output_dir)

    sections = build_bundle() if sections is None else sections
    generated_at = datetime.now(UTC)
    bundle_name = f"{BUNDLE_PREFIX}-{generated_at:%Y%m%d-%H%M%S}"

    path, descriptor = _create_bundle_file(output_dir, bundle_name)
    try:
        with os.fdopen(descriptor, "wb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as archive:
            for filename, value in sections.items():
                payload = _serialize(value)
                info = tarfile.TarInfo(f"{bundle_name}/{filename}")
                info.size = len(payload)
                info.mtime = int(time.time())
                archive.addfile(info, io.BytesIO(payload))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return BundleResult(
        path=path,
        bundle_name=bundle_name,
        sections=tuple(sections),
        size_bytes=path.stat().st_size,
    )
