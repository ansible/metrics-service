"""
Django signals for core models.
"""

import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .models import Organization, User

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """Handle User post-save signal."""
    if created:
        logger.info(f"User created: {instance.username} (ID: {instance.id})")
    else:
        logger.info(f"User updated: {instance.username} (ID: {instance.id})")


@receiver(pre_delete, sender=User)
def user_pre_delete(sender, instance, **kwargs):
    """Handle User pre-delete signal."""
    logger.info(f"User being deleted: {instance.username} (ID: {instance.id})")


@receiver(post_save, sender=Organization)
def organization_post_save(sender, instance, created, **kwargs):
    """Handle Organization post-save signal."""
    if created:
        logger.info(f"Organization created: {instance.name} (ID: {instance.id})")
    else:
        logger.info(f"Organization updated: {instance.name} (ID: {instance.id})")
