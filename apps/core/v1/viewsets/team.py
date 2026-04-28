from apps.core.models import Team
from apps.core.v1.serializers import TeamSerializer

from .base import BaseViewSet


class TeamViewSet(BaseViewSet):
    """CRUD viewset for Team resources with RBAC filtering."""

    queryset = Team.objects.all()
    serializer_class = TeamSerializer
