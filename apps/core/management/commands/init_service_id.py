"""
Management command to initialize ServiceID for ansible-base resource registry.

This command ensures that a ServiceID object exists in the database, which is
required by the ansible-base resource registry system.
"""

from ansible_base.resource_registry.models.service_identifier import (
    ServiceID,
)
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Initialize ServiceID for ansible-base resource registry"

    def handle(self, *args, **options):
        service_id_count = ServiceID.objects.count()

        if service_id_count == 0:
            service_id = ServiceID.objects.create()
            message = f"Created ServiceID: {service_id.pk}"
            self.stdout.write(self.style.SUCCESS(message))
        else:
            existing = ServiceID.objects.first()
            message = f"ServiceID exists: {existing.pk}"
            self.stdout.write(self.style.WARNING(message))
