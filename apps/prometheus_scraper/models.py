from django.db import models

try:
    from ansible_base.activitystream.models import AuditableModel
    from ansible_base.lib.abstract_models import CommonModel
except ImportError:

    class CommonModel(models.Model):
        id = models.BigAutoField(primary_key=True)
        created = models.DateTimeField(auto_now_add=True, help_text="The date/time this resource was created.")
        modified = models.DateTimeField(auto_now=True, help_text="The date/time this resource was created.")

        class Meta:
            abstract = True

    class AuditableModel(models.Model):
        class Meta:
            abstract = True


class PrometheusSnapshot(CommonModel, AuditableModel):
    """
    Raw Prometheus exposition text captured from a single scrape of one service.

    Snapshots are the raw, unprocessed output of a scrape — kept as-is so
    downstream processing can parse and aggregate them without re-scraping.
    Old snapshots should be cleaned up via a retention policy (see the
    cleanup_prometheus_snapshots task).
    """

    class Service(models.TextChoices):
        CONTROLLER = "controller", "Controller"
        EDA = "eda", "EDA"
        HUB = "hub", "Hub"

    class Status(models.TextChoices):
        OK = "ok", "OK"
        ERROR = "error", "Error"

    service = models.CharField(
        max_length=50,
        choices=Service.choices,
        db_index=True,
        help_text="The AAP service that was scraped",
    )
    scraped_at = models.DateTimeField(
        db_index=True,
        help_text="Timestamp when the scrape was initiated",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OK,
        help_text="Whether the scrape succeeded",
    )
    http_status = models.IntegerField(
        null=True,
        blank=True,
        help_text="HTTP response code returned by the target",
    )
    raw_text = models.TextField(
        blank=True,
        default="",
        help_text="Raw Prometheus exposition format text",
    )
    byte_count = models.IntegerField(
        default=0,
        help_text="Size of raw_text in bytes",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error details if status is 'error'",
    )

    class Meta:
        ordering = ["-scraped_at"]
        indexes = [
            models.Index(fields=["service", "scraped_at"]),
        ]

    def __str__(self):
        return f"PrometheusSnapshot({self.service}, {self.scraped_at}, {self.status})"

    def save(self, *args, **kwargs):
        self.byte_count = len(self.raw_text.encode("utf-8")) if self.raw_text else 0
        super().save(*args, **kwargs)
