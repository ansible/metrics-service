"""Resolve stored Controller organization IDs to stable DAB Resource UUIDs."""

from django.core.management.base import BaseCommand

from apps.dashboard_reports.awx_queries import fetch_controller_organizations
from apps.dashboard_reports.models import JobData
from apps.tasks.utils import get_db_connection


class Command(BaseCommand):
    """Backfill retained JobData organization identities from Controller Resource rows."""

    help = "Backfill JobData.organization_ansible_id from the Controller DAB resource registry."

    def handle(self, *args, **options):
        organizations = fetch_controller_organizations(get_db_connection("awx"))
        total_updated = 0
        for organization in organizations:
            if organization["ansible_id"] is None:
                continue
            total_updated += JobData.objects.filter(
                organization_id=organization["id"], organization_ansible_id__isnull=True
            ).update(organization_ansible_id=organization["ansible_id"])

        unresolved = JobData.objects.filter(organization_id__isnull=False, organization_ansible_id__isnull=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {total_updated} dashboard job rows; {unresolved} rows still have unresolved organization identities."
            )
        )
