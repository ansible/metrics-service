"""
Admin configuration for core models.
"""

from django.contrib import admin

from .models import (
    Organization,
    Team,
    User,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin for Organization model."""

    list_display = ("name", "created", "modified")
    search_fields = ("name", "description")
    filter_horizontal = ("users", "admins")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Admin for User model."""

    list_display = ("username", "email", "first_name", "last_name", "is_active")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Admin for Team model."""

    list_display = ("name", "organization", "created")
    list_filter = ("organization",)
    search_fields = ("name", "description", "organization__name")
    filter_horizontal = ("users", "admins", "team_parents")
