"""
Unit tests for apps/core/signals.py.
Targets 61.11% → ~100% coverage.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
def test_user_created_signal_fires():
    """Signal handler is called when a user is created."""
    with patch("apps.core.signals.logger") as mock_logger:
        user = User.objects.create_user(
            username="signal_test_user2",
            email="signal2@test.com",
            password="password123",  # noqa: S106
        )
    # info should have been called for the created path
    mock_logger.info.assert_called()
    args = mock_logger.info.call_args[0][0]
    assert "signal_test_user2" in args
    user.delete()


@pytest.mark.unit
@pytest.mark.django_db
def test_user_updated_signal_fires():
    """Signal handler is called when a user is saved (not created)."""
    user = User.objects.create_user(
        username="signal_update_user2",
        email="update2@test.com",
        password="password123",  # noqa: S106
    )

    with patch("apps.core.signals.logger") as mock_logger:
        user.first_name = "Updated"
        user.save()

    mock_logger.info.assert_called()
    args = mock_logger.info.call_args[0][0]
    assert "signal_update_user2" in args
    user.delete()


@pytest.mark.unit
@pytest.mark.django_db
def test_user_deleted_signal_fires():
    """pre_delete signal handler fires when a user is deleted."""
    user = User.objects.create_user(
        username="signal_delete_user2",
        email="delete2@test.com",
        password="password123",  # noqa: S106
    )

    with patch("apps.core.signals.logger") as mock_logger:
        user.delete()

    mock_logger.info.assert_called()
    args = mock_logger.info.call_args[0][0]
    assert "signal_delete_user2" in args


@pytest.mark.unit
@pytest.mark.django_db
def test_organization_created_signal_fires():
    """post_save signal fires on Organization creation."""
    from apps.core.models import Organization

    with patch("apps.core.signals.logger") as mock_logger:
        org = Organization.objects.create(name="Signal Test Org 2")

    mock_logger.info.assert_called()
    args = mock_logger.info.call_args[0][0]
    assert "Signal Test Org 2" in args
    org.delete()


@pytest.mark.unit
@pytest.mark.django_db
def test_organization_updated_signal_fires():
    """post_save signal fires on Organization update."""
    from apps.core.models import Organization

    org = Organization.objects.create(name="Update Org Signal 2")

    with patch("apps.core.signals.logger") as mock_logger:
        org.name = "Update Org Signal Renamed 2"
        org.save()

    mock_logger.info.assert_called()
    args = mock_logger.info.call_args[0][0]
    assert "Update Org Signal Renamed 2" in args
    org.delete()
