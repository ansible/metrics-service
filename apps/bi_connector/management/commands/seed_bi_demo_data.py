"""
Management command to seed the metrics-service database with realistic demo data.

Populates CollectionBatch, StoredHostMetric, StoredJobHostSummary,
HourlyMetricsCollection, and DailyMetricsSummary for BI connector demo / POC sign-off.

All seeding operations are idempotent — existing rows are skipped and a summary
of what was created vs. skipped is printed at the end.
"""

import json
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.bi_connector.models import CollectionBatch, StoredHostMetric, StoredJobHostSummary
from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection
from apps.tasks.services import OutputFormatter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENV_CYCLE = ["prod", "staging", "dev"]

_HOURLY_COLLECTOR_TYPES = [
    "job_host_summary_service",
    "unified_jobs",
    "credentials_service",
]

_DAILY_COLLECTOR_TYPES = _HOURLY_COLLECTOR_TYPES  # same set for daily aggregation


class Command(BaseCommand):
    """Seed the metrics-service database with realistic BI connector demo data."""

    help = "Populate the database with demo data for a BI connector demo / POC sign-off"

    def __init__(self, *args, **kwargs):
        """Initialise the command with an OutputFormatter helper."""
        super().__init__(*args, **kwargs)
        self.output: OutputFormatter  # assigned in handle()

    # ------------------------------------------------------------------
    # Django management command interface
    # ------------------------------------------------------------------

    def add_arguments(self, parser) -> None:
        """Add optional arguments for the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing to the database",
        )

    def handle(self, *args, **options) -> None:
        """Entry point — coordinate all seeding steps and print a final summary."""
        self.output = OutputFormatter(self.stdout, self.style)
        dry_run: bool = options.get("dry_run", False)

        if dry_run:
            self.output.warning("DRY RUN — no data will be written")

        self.output.write("")
        self.output.write("BI Connector Demo Data Seeder")
        self.output.write_separator()

        now = timezone.now()

        batches = self._seed_collection_batches(now, dry_run)
        host_metrics_created = self._seed_stored_host_metrics(now, batches, dry_run)
        job_summaries_created = self._seed_stored_job_host_summaries(now, batches, dry_run)
        hourly_created = self._seed_hourly_metrics_collections(now, dry_run)
        daily_created = self._seed_daily_metrics_summaries(now, dry_run)

        self.output.write("")
        self.output.write_separator()
        self.output.success("Seeding complete. Summary:")
        self.output.write(f"  CollectionBatch      : {len(batches)} total (see detail above)")
        self.output.write(f"  StoredHostMetric     : {host_metrics_created} created")
        self.output.write(f"  StoredJobHostSummary : {job_summaries_created} created")
        self.output.write(f"  HourlyMetricsCollection : {hourly_created} created")
        self.output.write(f"  DailyMetricsSummary  : {daily_created} created")

    # ------------------------------------------------------------------
    # Seeding helpers
    # ------------------------------------------------------------------

    def _seed_collection_batches(self, now, dry_run: bool) -> list[CollectionBatch]:
        """
        Seed five CollectionBatch records covering the last 7 days.

        Returns the list of CollectionBatch instances (fetched or created).
        """
        self.output.write("")
        self.output.write("Seeding CollectionBatch records …")

        seven_days_ago = now - timedelta(days=7)
        three_days_ago = now - timedelta(days=3)

        batch_specs = [
            # (collector_type, since, until, records_imported)
            ("main_host_daily", seven_days_ago, three_days_ago, 65),
            ("main_host_daily", three_days_ago, now, 38),
            ("job_host_summary", seven_days_ago, three_days_ago, 180),
            ("job_host_summary", three_days_ago, now, 95),
            ("main_indirectmanagednodeaudit", seven_days_ago, now, 12),
        ]

        batches: list[CollectionBatch] = []
        created_count = 0
        skipped_count = 0

        for collector_type, since, until, records_imported in batch_specs:
            if dry_run:
                self.output.write(f"  [dry-run] Would create CollectionBatch({collector_type})")
                # Create an in-memory placeholder so downstream seeders don't crash
                instance = CollectionBatch(
                    collector_type=collector_type,
                    batch_type="scheduled",
                    status="completed",
                    since=since,
                    until=until,
                    records_imported=records_imported,
                    started_at=since,
                    completed_at=until,
                )
                batches.append(instance)
                continue

            instance, created = CollectionBatch.objects.get_or_create(
                collector_type=collector_type,
                since=since,
                until=until,
                defaults={
                    "batch_type": "scheduled",
                    "status": "completed",
                    "records_imported": records_imported,
                    "started_at": since,
                    "completed_at": until,
                },
            )
            batches.append(instance)
            if created:
                created_count += 1
            else:
                skipped_count += 1

        self.output.write(f"  CollectionBatch: {created_count} created, {skipped_count} already existed")
        return batches

    def _make_hostname(self, i: int) -> str:
        """Return a deterministic hostname for seed index *i* (1-based)."""
        env = _ENV_CYCLE[(i - 1) % len(_ENV_CYCLE)]
        return f"host-{i:03d}.{env}.example.com"

    def _seed_stored_host_metrics(self, now, batches: list[CollectionBatch], dry_run: bool) -> int:
        """
        Seed 100 StoredHostMetric records (skip if count >= 100).

        Returns the number of records created.
        """
        self.output.write("")
        self.output.write("Seeding StoredHostMetric records …")

        if not dry_run and StoredHostMetric.objects.count() >= 100:
            self.output.write("  StoredHostMetric: already >= 100 rows, skipping")
            return 0

        # Pick a CollectionBatch to attach host metrics to (first main_host_daily batch)
        host_batch = next((b for b in batches if b.collector_type == "main_host_daily"), batches[0])

        created_count = 0
        for i in range(1, 101):
            hostname = self._make_hostname(i)
            deleted = i > 90  # last 10 are deleted

            # Vary first_automation between 12 and 18 months ago
            months_ago = 12 + (i % 7)  # cycles 12-18
            first_automation = now - timedelta(days=months_ago * 30)

            # Vary last_automation between 1 and 90 days ago
            last_automation = now - timedelta(days=((i * 7) % 90) + 1)

            automated_counter = random.randint(10, 500)
            deleted_counter = random.randint(1, 5) if deleted else 0

            if dry_run:
                self.output.write(f"  [dry-run] Would create StoredHostMetric({hostname})")
                created_count += 1
                continue

            _, created = StoredHostMetric.objects.get_or_create(
                hostname=hostname,
                defaults={
                    "host_id": i,
                    "first_automation": first_automation,
                    "last_automation": last_automation,
                    "automated_counter": automated_counter,
                    "deleted_counter": deleted_counter,
                    "deleted": deleted,
                    "collection_batch": host_batch if host_batch.pk else None,
                },
            )
            if created:
                created_count += 1

        self.output.write(f"  StoredHostMetric: {created_count} created")
        return created_count

    def _seed_stored_job_host_summaries(self, now, batches: list[CollectionBatch], dry_run: bool) -> int:
        """
        Seed 300 StoredJobHostSummary records (skip if count >= 300).

        Returns the number of records created.
        """
        self.output.write("")
        self.output.write("Seeding StoredJobHostSummary records …")

        if not dry_run and StoredJobHostSummary.objects.count() >= 300:
            self.output.write("  StoredJobHostSummary: already >= 300 rows, skipping")
            return 0

        jhs_batch = next((b for b in batches if b.collector_type == "job_host_summary"), batches[0])

        created_count = 0
        for i in range(300):
            summary_id = 10000 + i
            host_id = (i % 100) + 1
            job_id = (i // 5) + 1
            host_name = self._make_hostname(host_id)
            organization_id = (i % 3) + 1
            inventory_id = (i % 5) + 1
            # Stagger modified timestamps over the last 30 days
            modified = now - timedelta(days=(i % 30), hours=(i % 24))

            if dry_run:
                self.output.write(f"  [dry-run] Would create StoredJobHostSummary(summary_id={summary_id})")
                created_count += 1
                continue

            _, created = StoredJobHostSummary.objects.get_or_create(
                summary_id=summary_id,
                defaults={
                    "host_id": host_id,
                    "job_id": job_id,
                    "host_name": host_name,
                    "organization_id": organization_id,
                    "inventory_id": inventory_id,
                    "modified": modified,
                    "collection_batch": jhs_batch if jhs_batch.pk else None,
                },
            )
            if created:
                created_count += 1

        self.output.write(f"  StoredJobHostSummary: {created_count} created")
        return created_count

    def _build_hourly_raw_data(self, collector_type: str, n: int) -> dict:
        """
        Build a realistic raw_data dict for *collector_type* with cardinality *n*.

        Args:
            collector_type: One of the seeded hourly collector type strings.
            n: A random integer in 5–50 representing the base cardinality for this hour.

        Returns:
            A dict suitable for HourlyMetricsCollection.raw_data.
        """
        if collector_type == "job_host_summary_service":
            return {
                "total_hosts": n,
                "total_summaries": n * 3,
                "success_count": n * 2,
                "failed_count": n,
            }
        if collector_type == "unified_jobs":
            return {
                "total_jobs": n,
                "successful": int(n * 0.8),
                "failed": int(n * 0.15),
                "canceled": int(n * 0.05),
            }
        # credentials_service
        return {
            "total": n,
            "by_type": {
                "ssh": int(n * 0.5),
                "vault": int(n * 0.25),
                "aws": int(n * 0.25),
            },
        }

    def _seed_hourly_metrics_collections(self, now, dry_run: bool) -> int:
        """
        Seed 7 days * 24 hours * 3 collector types = 504 HourlyMetricsCollection records.

        Skips entirely if the count is already >= 400.
        Returns the number of records created.
        """
        self.output.write("")
        self.output.write("Seeding HourlyMetricsCollection records …")

        if not dry_run and HourlyMetricsCollection.objects.count() >= 400:
            self.output.write("  HourlyMetricsCollection: already >= 400 rows, skipping")
            return 0

        # Truncate *now* to the start of the current hour so timestamps are clean
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        created_count = 0
        for day_offset in range(7):
            for hour_offset in range(24):
                ts = current_hour - timedelta(days=day_offset, hours=hour_offset)
                for collector_type in _HOURLY_COLLECTOR_TYPES:
                    n = random.randint(5, 50)
                    raw_data = self._build_hourly_raw_data(collector_type, n)
                    data_size_bytes = len(json.dumps(raw_data).encode())

                    if dry_run:
                        created_count += 1
                        continue

                    _, created = HourlyMetricsCollection.objects.get_or_create(
                        collector_type=collector_type,
                        collection_timestamp=ts,
                        defaults={
                            "raw_data": raw_data,
                            "status": "collected",
                            "data_size_bytes": data_size_bytes,
                        },
                    )
                    if created:
                        created_count += 1

        if dry_run:
            self.output.write(f"  [dry-run] Would create {created_count} HourlyMetricsCollection records")
        else:
            self.output.write(f"  HourlyMetricsCollection: {created_count} created")
        return created_count

    def _build_daily_aggregated_metrics(self, day_offset: int) -> dict:
        """
        Build an aggregated_metrics dict for a daily summary.

        The day_offset (0 = today, 29 = oldest) is used to vary values so
        each day looks slightly different in BI tools.

        Args:
            day_offset: How many days ago this summary covers (0 = today).

        Returns:
            A dict with per-collector-type aggregated figures.
        """
        base = max(5, 50 - day_offset)  # older days have slightly fewer events
        return {
            "job_host_summary_service": {
                "total_hosts": base * 24,
                "total_summaries": base * 24 * 3,
                "success_count": base * 24 * 2,
                "failed_count": base * 24,
            },
            "unified_jobs": {
                "total_jobs": base * 24,
                "successful": int(base * 24 * 0.8),
                "failed": int(base * 24 * 0.15),
                "canceled": int(base * 24 * 0.05),
            },
            "credentials_service": {
                "total": base * 24,
                "by_type": {
                    "ssh": int(base * 24 * 0.5),
                    "vault": int(base * 24 * 0.25),
                    "aws": int(base * 24 * 0.25),
                },
            },
        }

    def _seed_daily_metrics_summaries(self, now, dry_run: bool) -> int:
        """
        Seed one DailyMetricsSummary per day for the last 30 days (skip if count >= 30).

        Returns the number of records created.
        """
        self.output.write("")
        self.output.write("Seeding DailyMetricsSummary records …")

        if not dry_run and DailyMetricsSummary.objects.count() >= 30:
            self.output.write("  DailyMetricsSummary: already >= 30 rows, skipping")
            return 0

        today = now.date()
        created_count = 0

        for day_offset in range(30):
            summary_date = today - timedelta(days=day_offset)
            # Days older than 7 have no seeded hourly records, so count is 0 for those
            hourly_collections_count = 24 * len(_HOURLY_COLLECTOR_TYPES) if day_offset < 7 else 0
            aggregated_metrics = self._build_daily_aggregated_metrics(day_offset)

            if dry_run:
                self.output.write(f"  [dry-run] Would create DailyMetricsSummary({summary_date})")
                created_count += 1
                continue

            _, created = DailyMetricsSummary.objects.get_or_create(
                summary_date=summary_date,
                defaults={
                    "status": "aggregated",
                    "aggregated_metrics": aggregated_metrics,
                    "hourly_collections_count": hourly_collections_count,
                    "missing_hours": [],
                },
            )
            if created:
                created_count += 1

        self.output.write(f"  DailyMetricsSummary: {created_count} created")
        return created_count
