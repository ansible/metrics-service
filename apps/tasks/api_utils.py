"""
API utility functions for the metrics service.

This module provides reusable utility functions for API operations.
"""

import logging
from typing import Any

from django.utils import timezone
from rest_framework import serializers

logger = logging.getLogger(__name__)


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()
    status_code = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
    details = serializers.DictField(required=False)


def build_error_response(message: str, details: dict[str, Any] | None = None, status_code: int = 400) -> dict[str, Any]:
    """
    Build a standardized error response dictionary.

    This function provides a consistent format for error responses,
    reducing duplication across view error handling.

    Args:
        message (str): Main error message
        details (dict): Optional additional error details
        status_code (int): HTTP status code for the error

    Returns:
        dict: Standardized error response
    """
    error_response = {
        "error": message,
        "status_code": status_code,
        "timestamp": timezone.now().isoformat(),
    }

    if details:
        error_response["details"] = details

    return error_response
