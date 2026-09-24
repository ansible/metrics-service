from ansible_base.lib.abstract_models.organization import AbstractOrganization
from django.db import models


class Organization(AbstractOrganization):
    """
    Organization model using DAB's AbstractOrganization.

    Organizations serve as the top-level container for teams and resources.
    """

    objects = models.Manager()

    class Meta:
        permissions = [
            ("member_organization", "User is member of this organization"),
            ("view_automation_dashboard", "Can view organization automation dashboard data"),
            ("change_automation_dashboard", "Can edit organization automation dashboard settings"),
        ]
