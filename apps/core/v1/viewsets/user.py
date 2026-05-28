from ansible_base.rbac.api.permissions import AnsibleBaseUserPermissions
from ansible_base.rbac.policies import visible_users
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.models import User
from apps.core.v1.serializers import UserSerializer

from .base import BaseViewSet


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of users.",
        description="Returns a list of users.",
    ),
    retrieve=extend_schema(
        summary="Get a specific user by ID.",
        description="Returns a specific user by ID.",
    ),
    create=extend_schema(
        summary="Create a user.",
        description="Create a new user object",
        request=UserSerializer,
    ),
    update=extend_schema(
        summary="Update a specific user by ID.",
        description="Update a specific user by ID.",
    ),
    partial_update=extend_schema(
        summary="Partially update a specific user by ID.",
        description="Partially update a specific user by ID.",
    ),
    destroy=extend_schema(
        summary="Delete a specific user by ID.",
        description="Delete a specific user by ID.",
    ),
)
class UserViewSet(BaseViewSet):
    """CRUD viewset for User resources, restricted to visible users per DAB policy."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AnsibleBaseUserPermissions]

    def filter_queryset(self, queryset):
        """Restrict queryset to users visible to the requesting user."""
        queryset = visible_users(self.request.user, queryset=queryset)
        return super(BaseViewSet, self).filter_queryset(queryset)

    @extend_schema(
        summary="Get current user details",
        description="Get currently logged in user's details",
        responses={200: UserSerializer},
    )
    @action(detail=False, methods=["get"])
    def me(self, request):
        """Return the profile of the currently authenticated user."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
