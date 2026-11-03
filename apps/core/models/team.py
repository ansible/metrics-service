from ansible_base.lib.abstract_models.team import AbstractTeam
from ansible_base.resource_registry.fields import AnsibleResourceField
from django.db import models


class Team(AbstractTeam):
    """
    Team model using DAB's AbstractTeam.

    Teams belong to organizations and group users for access control.
    The organization FK is inherited from AbstractTeam and uses
    settings.ANSIBLE_BASE_ORGANIZATION_MODEL.
    """

    objects = models.Manager()

    # Exposes the team's Resource Registry row as `.resource`. DAB's RBAC API
    # prefetches `team__resource` when listing role team assignments; without
    # this field that lookup fails once a team holds a role.
    resource = AnsibleResourceField(primary_key_field="id")

    class Meta:
        permissions = [("member_team", "Has all roles assigned to this team")]
