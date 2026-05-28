from ansible_base.lib.utils.views.ansible_base import AnsibleBaseView
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class PingView(AnsibleBaseView):
    """
    Simple ping endpoint to verify the service is running.

    Returns a simple "pong" response with HTTP 200.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Ping server",
        description="Simple ping endpoint to verify the service is running.",
        responses={
            200: inline_serializer(
                name="PingSerializer",
                fields={"ping": serializers.CharField()},
            ),
        },
    )
    def get(self, request):
        return Response({"ping": "pong"}, status=status.HTTP_200_OK)
