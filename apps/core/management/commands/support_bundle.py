"""Read-only diagnostic support bundle.

Usage::

    metrics-service support-bundle [--output-dir PATH] [--dry-run]

Writes a ``support-bundle-YYYYMMDD-HHMMSS.tar.gz`` containing exactly
``tasks.json``, ``ingestion.json``, ``queues.json``, ``schema.json`` and
``settings.json``. Every section is redacted before serialisation.

The command never takes locks and never writes outside the output tarball, so it
is safe to run on a live instance. The tarball is created with mode ``0600`` and
``O_CREAT | O_EXCL``: an existing file or a pre-planted symlink is never
overwritten (a same-second run gets a ``-2`` suffix instead).
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.support_bundle import SupportBundleError, build_bundle, manifest, write_tarball


class Command(BaseCommand):
    help = "Collect read-only diagnostic data into a support bundle tarball."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=None,
            help=(
                "Directory to write the tarball into. Created files are 0600; existing files are never "
                "overwritten. Defaults to the current working directory."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print a manifest of the bundle contents without writing any file.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        try:
            if dry_run:
                self.stdout.write(json.dumps(manifest(build_bundle()), indent=2))
                return None

            output_dir = Path(options["output_dir"]).expanduser() if options["output_dir"] else Path.cwd()
            result = write_tarball(output_dir)
        except SupportBundleError as exc:
            raise CommandError(str(exc)) from exc
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface a clean error, never a traceback
            raise CommandError(f"Failed to build support bundle: {exc}") from exc

        if options.get("verbosity", 1) > 0:
            self.stdout.write(f"Support bundle written to: {result.path}")
        return None
