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

from django.core.management.base import CommandError

from apps.core.support_bundle.collectors import (
    collect_ingestion,
    collect_meta,
    collect_queues,
    collect_schema,
    collect_settings,
    collect_tasks,
)

BUNDLE_FILES = ("tasks.json", "ingestion.json", "queues.json", "schema.json", "settings.json")
BUNDLE_PREFIX = "support-bundle"


@dataclass(frozen=True)
class BundleResult:
    """Location and shape of a written support bundle."""

    path: Path
    bundle_name: str
    sections: tuple[str, ...]
    size_bytes: int


def build_bundle() -> dict[str, Any]:
    """Run every collector and return an ordered ``{filename: data}`` mapping."""
    meta = collect_meta()
    sections: dict[str, Any] = {
        "tasks.json": collect_tasks(),
        "ingestion.json": collect_ingestion(),
        "queues.json": collect_queues(),
        "schema.json": collect_schema(),
        "settings.json": collect_settings(),
    }
    for section in sections.values():
        if isinstance(section, dict):
            section.setdefault("meta", meta)
    return sections


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
    if not output_dir.exists() or not output_dir.is_dir():
        raise CommandError(f"Output directory does not exist or is not a directory: {output_dir}")
    if not os.access(output_dir, os.W_OK):
        raise CommandError(f"Output directory is not writable: {output_dir}")


def write_tarball(output_dir: str | Path, sections: dict[str, Any] | None = None) -> BundleResult:
    """Write *sections* as ``<output_dir>/support-bundle-YYYYMMDD-HHMMSS.tar.gz``."""
    output_dir = Path(output_dir)
    _validate_output_dir(output_dir)

    sections = build_bundle() if sections is None else sections
    generated_at = datetime.now(UTC)
    bundle_name = f"{BUNDLE_PREFIX}-{generated_at:%Y%m%d-%H%M%S}"

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for filename, value in sections.items():
            payload = _serialize(value)
            info = tarfile.TarInfo(f"{bundle_name}/{filename}")
            info.size = len(payload)
            info.mtime = int(time.time())
            archive.addfile(info, io.BytesIO(payload))

    path = (output_dir / f"{bundle_name}.tar.gz").resolve()
    path.write_bytes(buffer.getvalue())
    return BundleResult(
        path=path,
        bundle_name=bundle_name,
        sections=tuple(sections),
        size_bytes=path.stat().st_size,
    )
