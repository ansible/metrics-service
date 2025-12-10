"""Team model with hierarchical organization support."""

from ansible_base.lib.abstract_models.team import AbstractTeam
from ansible_base.resource_registry.fields import AnsibleResourceField
from django.db import models

from .mixins import AccessControlMixin, UserRelatedMixin
from .user import User


class Team(AbstractTeam, AccessControlMixin, UserRelatedMixin):
    """
    Team model with hierarchical organization support.

    This model represents a team within an organization that can contain
    users and admins, with support for team hierarchies.
    """

    class Meta:
        ordering = ["id"]
        abstract = False
        unique_together = [("organization", "name")]
        permissions = [("member_team", "Has all roles assigned to this team")]

    resource = AnsibleResourceField(primary_key_field="id")

    team_parents = models.ManyToManyField(
        "Team",
        related_name="team_children",
        blank=True,
        help_text="Parent teams for hierarchy support",
    )

    # Override UserRelatedMixin fields to use proper User model and related_name
    users = models.ManyToManyField(
        User,
        related_name="teams",
        blank=True,
        help_text="The list of users on this team",
    )

    admins = models.ManyToManyField(
        User,
        related_name="teams_administered",
        blank=True,
        help_text="The list of admins for this team",
    )

    # Relations to ignore for certain operations
    ignore_relations = []

    @classmethod
    def access_qs(cls, user, queryset=None):
        """
        Return queryset filtered by user permissions.
        Includes system auditor logic for read-only access to all teams.
        """
        if queryset is None:
            queryset = cls.objects.all()

        # System administrators can see all teams
        if user.is_superuser:
            return queryset

        # System auditors can see all teams (read-only)
        if hasattr(user, "is_system_auditor_user") and user.is_system_auditor_user():
            return queryset

        # Regular users: filter by organization and team membership
        user_organizations = user.member_of_organizations.all()

        accessible_teams = queryset.filter(
            models.Q(organization__in=user_organizations)  # Teams in user's orgs
            | models.Q(users=user)  # Teams user is member of
            | models.Q(admins=user)  # Teams user administers
        ).distinct()

        return accessible_teams

    def __str__(self):
        """
        Return string representation of the team.

        Returns:
            str: Organization name and team name
        """
        return f"{self.organization.name} - {self.name}"
