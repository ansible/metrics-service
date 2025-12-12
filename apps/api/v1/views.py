"""
API v1 views for metrics_service following AAP standards.
"""

from ansible_base.lib.utils.views.django_app_api import AnsibleBaseDjangoAppApiView
from ansible_base.rbac import permission_registry
from ansible_base.rbac.api.permissions import AnsibleBaseObjectPermissions, AnsibleBaseUserPermissions
from ansible_base.rbac.policies import visible_users
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core.models import Organization, Team, User

from .serializers import OrganizationSerializer, TeamSerializer, UserSerializer


class BaseViewSet(ModelViewSet, AnsibleBaseDjangoAppApiView):
    """Base viewset with RBAC filtering."""

    permission_classes = [AnsibleBaseObjectPermissions]

    def filter_queryset(self, qs):
        cls = qs.model
        if hasattr(cls, "access_qs"):
            qs = cls.access_qs(self.request.user, queryset=qs)
        return super().filter_queryset(qs)


class OrganizationViewSet(BaseViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


class TeamViewSet(BaseViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer


class UserViewSet(BaseViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AnsibleBaseUserPermissions]

    def filter_queryset(self, qs):
        # Only use visible_users if RBAC is properly set up (Organization registered)
        if permission_registry.is_registered(Organization):
            qs = visible_users(self.request.user, queryset=qs)
        return super(BaseViewSet, self).filter_queryset(qs)

    @action(detail=False, methods=["get"])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
