"""Organization model with user and admin management capabilities."""

from ansible_base.lib.abstract_models.organization import AbstractOrganization
from ansible_base.resource_registry.fields import AnsibleResourceField
from django.db import models

from .mixins import AccessControlMixin, UserRelatedMixin


class Organization(AbstractOrganization, AccessControlMixin, UserRelatedMixin):
    """
    Organization model with user and admin management capabilities.

    This model represents an organization that can contain users and admins.
    It inherits from AbstractOrganization for DAB compatibility and includes
    access control functionality through AccessControlMixin.
    """

    class Meta:
        ordering = ["id"]
        permissions = [
            ("member_organization", "User is member of this organization"),
        ]

    resource = AnsibleResourceField(primary_key_field="id")

    # UserRelatedMixin provides users and admins fields
    # Override to customize related_name for organizations
    users = models.ManyToManyField(
        "User",
        related_name="member_of_organizations",
        blank=True,
        help_text="The list of users on this organization",
    )

    admins = models.ManyToManyField(
        "User",
        related_name="admin_of_organizations",
        blank=True,
        help_text="The list of admins for this organization",
    )

    # Example custom field - replace or remove as needed
    extra_field = models.CharField(max_length=100, blank=True, default="")

    @classmethod
    def access_qs(cls, user, queryset=None):
        """
        Return queryset filtered by user permissions.
        Includes system auditor logic for read-only access to all organizations.
        """
        if queryset is None:
            queryset = cls.objects.all()

        # System administrators can see everything
        if user.is_superuser:
            return queryset

        # System auditors can see all organizations (read-only)
        if hasattr(user, "is_system_auditor") and getattr(user, "is_system_auditor", False):
            return queryset

        # Regular users: filter by organization membership
        # Only show organizations where user is a member or admin
        user_orgs = queryset.filter(models.Q(users=user) | models.Q(admins=user)).distinct()

        return user_orgs

    def __str__(self):
        """
        Return string representation of the organization.

        Returns:
            str: Organization name
        """
        return self.name
