from ansible_base.lib.serializers.common import NamedCommonModelSerializer
from ansible_base.rbac.api.related import RelatedAccessMixin

from apps.core.models import Team


class TeamSerializer(RelatedAccessMixin, NamedCommonModelSerializer):
    """Serializer for the Team model with RBAC access mixin."""

    class Meta:
        """Serializer meta configuration for TeamSerializer."""

        model = Team
        fields = "__all__"
