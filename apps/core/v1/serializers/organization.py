from ansible_base.lib.serializers.common import NamedCommonModelSerializer
from ansible_base.rbac.api.related import RelatedAccessMixin

from apps.core.models import Organization


class OrganizationSerializer(RelatedAccessMixin, NamedCommonModelSerializer):
    """Serializer for the Organization model with RBAC access mixin."""

    class Meta:
        """Serializer meta configuration for OrganizationSerializer."""

        model = Organization
        fields = "__all__"
