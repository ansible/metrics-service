"""Ephemeral runtime log level override for the service.

A single row stores the operator-requested log level that running processes
apply at bounded refresh points. It is intentionally *not* configuration:
it expires, it is ignored by processes that started after it was written,
and it is never persisted to dynaconf, env files, or the /etc override path.
"""

import logging

from ansible_base.lib.abstract_models import CommonModel
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

LEVEL_CHOICES = [
    ("DEBUG", "DEBUG"),
    ("INFO", "INFO"),
    ("WARNING", "WARNING"),
    ("ERROR", "ERROR"),
    ("CRITICAL", "CRITICAL"),
]

SINGLETON_PK = 1


class RuntimeLogLevelOverride(CommonModel):
    """The active, time-bounded runtime log level override.

    Exactly one row exists. Callers should use
    :mod:`apps.core.logging_control` rather than touching this model directly;
    that module owns validation, TTL handling, and process-start semantics.
    """

    level = models.CharField(max_length=16, choices=LEVEL_CHOICES)
    expires_at = models.DateTimeField(help_text="When the override stops being applied.")
    set_by = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Free-form actor description, e.g. 'cli:hostname:user'.",
    )

    class Meta:
        verbose_name = "runtime log level override"
        verbose_name_plural = "runtime log level override"

    def save(self, *args, **kwargs):
        """Force a singleton row and remove any stragglers."""
        self.pk = SINGLETON_PK
        # ``Model.objects.create()`` passes force_insert=True, which would
        # bypass the singleton and raise a duplicate-key error on the second
        # write. Drop it and let Django choose INSERT vs UPDATE from
        # _state.adding, which we set from whether the row already exists.
        kwargs.pop("force_insert", None)
        existing = type(self).objects.filter(pk=SINGLETON_PK).first()
        if existing is None:
            self._state.adding = True
        else:
            self._state.adding = False
            # UPDATE writes every concrete field; preserve auto_now_add values
            # that this (possibly fresh) instance has not populated.
            if self.created is None:
                self.created = existing.created
            if self.modified is None:
                self.modified = existing.modified
        super().save(*args, **kwargs)
        type(self).objects.exclude(pk=SINGLETON_PK).delete()

    @property
    def is_expired(self) -> bool:
        """True when the override's TTL has elapsed."""
        return self.expires_at <= timezone.now()

    def __str__(self) -> str:
        actor = self.set_by or "unknown"
        return f"{self.level} until {self.expires_at.isoformat()} (set by {actor})"
