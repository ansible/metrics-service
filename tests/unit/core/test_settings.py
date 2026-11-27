"""Tests for cross-environment settings invariants."""

import pytest
from django.conf import settings


@pytest.mark.unit
def test_default_renderer_classes_include_service_renderer():
    assert settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == [
        "rest_framework.renderers.JSONRenderer",
        "apps.core.renderers.ServiceBrowsableAPIRenderer",
    ]
