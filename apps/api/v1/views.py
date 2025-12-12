"""
API v1 views for metrics_service following AAP standards.
"""

from ansible_base.lib.utils.views.django_app_api import AnsibleBaseDjangoAppApiView
from ansible_base.rbac import permission_registry
from ansible_base.rbac.api.permissions import AnsibleBaseObjectPermissions, AnsibleBaseUserPermissions
from ansible_base.rbac.policies import visible_users
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core.models import Organization, Team, User
from apps.core.utils import log_setting_change
from metrics_service.settings import DYNACONF

from .serializers import OrganizationSerializer, TeamSerializer, UserSerializer


class SettingView(AnsibleBaseDjangoAppApiView, viewsets.ViewSet):
    permission_classes = [IsAdminUser, AnsibleBaseObjectPermissions]

    def _get_current_settings(self):
        """Helper to get serializable settings."""
        setting_dict = DYNACONF.to_dict()

        # Convert any PosixPath objects to strings
        def serialize_value(value):
            from pathlib import Path

            if isinstance(value, Path):
                return str(value)
            elif isinstance(value, dict):
                return {k: serialize_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [serialize_value(item) for item in value]
            return value

        return serialize_value(setting_dict)

    def list(self, request):
        """Get all current configuration settings from DYNACONF."""
        return Response(self._get_current_settings())

    def update(self, request):
        """
        Update configuration settings (PUT).

        Expects body like: {"DEBUG": true, "SECRET_KEY": "xyz"}
        """
        # First validate that all keys exist in DYNACONF
        existing_settings = DYNACONF.as_dict()
        for key in request.data:
            if key not in existing_settings:
                return Response(
                    {"error": f"Setting '{key}' does not exist. Cannot create new settings."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Take a snapshot of current settings before change
        old_settings = {}
        for key in request.data:
            old_settings[key] = DYNACONF.get(key)

        # Update DYNACONF and log each change
        for key, new_value in request.data.items():
            DYNACONF.set(key, new_value)
            log_setting_change(
                user=request.user,
                setting_key=key,
                new_value=new_value,
                old_value=old_settings.get(key),  # Pass the old DYNACONF value
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    def partial_update(self, request):
        """
        Update configuration settings (PATCH).

        Expects body like: {"DEBUG": true}
        """
        # Same implementation as update() for settings
        # (No difference between PUT and PATCH for a singleton resource)
        return self.update(request)

    @action(detail=False, methods=["post"])
    def reload(self, request):
        """Reload configuration from files and log changes."""
        try:
            # Take a snapshot of current settings before reload
            old_settings = DYNACONF.as_dict()
            # Reload the configuration
            DYNACONF.reload()
            # Get new settings and find what changed
            new_settings = DYNACONF.as_dict()

            for key in new_settings:
                old_value = old_settings.get(key)
                new_value = new_settings.get(key)

                # Only log if the value actually changed
                if old_value != new_value:
                    log_setting_change(
                        user=request.user,
                        setting_key=key,
                        new_value=new_value,
                        old_value=old_value,  # Pass the old DYNACONF value
                    )

            return Response({"message": "Configuration reloaded successfully"}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["post"], url_path="rollback/(?P<change_id>[0-9]+)")
    def rollback(self, request, change_id=None):
        """
        Rollback a configuration change by ID.
        """
        from apps.core.utils import rollback_configuration_change

        result = rollback_configuration_change(change_id=change_id, user=request.user)

        if result["success"]:
            return Response(result, status=status.HTTP_200_OK)
        else:
            status_code = status.HTTP_404_NOT_FOUND if "not found" in result["error"] else status.HTTP_400_BAD_REQUEST
            return Response({"error": result["error"]}, status=status_code)


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
