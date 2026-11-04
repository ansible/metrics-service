"""Change the service log level on a running deployment without a restart."""

import os
import socket

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core import logging_control


def _actor() -> str:
    host = socket.gethostname() or "unknown-host"
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown-user"
    return f"cli:{host}:{user}"


class Command(BaseCommand):
    """Set, show, or clear the ephemeral runtime log level override."""

    help = (
        "Change the log level of the running metrics-service without restarting it. "
        "The change is shared through the database and expires automatically."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "level",
            nargs="?",
            choices=list(logging_control.LEVEL_NAMES),
            help="Log level to apply. Required unless --show or --clear is used.",
        )
        parser.add_argument(
            "--ttl",
            type=int,
            default=None,
            help=(
                "Seconds before the override expires. "
                f"Defaults to RUNTIME_LOG_LEVEL_MAX_TTL ({getattr(settings, 'RUNTIME_LOG_LEVEL_MAX_TTL', 3600)})."
            ),
        )
        parser.add_argument("--show", action="store_true", help="Show the active override and exit.")
        parser.add_argument("--clear", action="store_true", help="Remove the override and exit.")
        parser.add_argument(
            "--local",
            action="store_true",
            help="Also apply the level to this short-lived command process (smoke testing).",
        )

    def handle(self, *args, **options):
        if options["show"] and options["clear"]:
            raise CommandError("--show and --clear are mutually exclusive")

        if options["show"]:
            self._show()
            return

        if options["clear"]:
            self._clear(local=options["local"])
            return

        level = options["level"]
        if not level:
            raise CommandError("LEVEL is required unless --show or --clear is used")

        try:
            override = logging_control.set_override(
                level,
                ttl_seconds=options["ttl"],
                actor=_actor(),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if options["local"]:
            logging_control.apply_level(override.level)

        logging_control.notify_dispatcherd(override.level)

        refresh = getattr(settings, "RUNTIME_LOG_LEVEL_REFRESH_SECONDS", 1)
        self.stdout.write(
            self.style.SUCCESS(
                f"Log level set to {override.level} until {override.expires_at.isoformat()} (set by {override.set_by})."
            )
        )
        self.stdout.write(
            "Running processes apply the change within one request/task cycle "
            f"(refresh interval: {refresh}s). Restarting the service reverts to "
            f"{logging_control.BASELINE_LEVEL}."
        )

    def _show(self):
        override = logging_control.get_active_override()
        if override is None:
            self.stdout.write(f"No override set (using baseline {logging_control.BASELINE_LEVEL}).")
            return
        state = "expired" if override.is_expired else "active"
        self.stdout.write(
            f"Override: level={override.level} expires_at={override.expires_at.isoformat()} "
            f"set_by={override.set_by or 'unknown'} modified={override.modified.isoformat()} ({state})."
        )
        if override.is_expired:
            self.stdout.write(f"Expired overrides are ignored; processes are using {logging_control.BASELINE_LEVEL}.")

    def _clear(self, local: bool = False):
        deleted = logging_control.clear_override()
        if local:
            logging_control.revert()
        if deleted:
            self.stdout.write(self.style.SUCCESS("Runtime log level override cleared."))
        else:
            self.stdout.write("No runtime log level override was set.")
