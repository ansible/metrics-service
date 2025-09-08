"""
Admin configuration for core models.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Animal,
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


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    """Admin for Animal model."""

    list_display = ("name", "kind", "owner", "age")
    list_filter = ("kind",)
    search_fields = ("name", "owner__username")
    filter_horizontal = ("people_friends",)


# Task-related admin classes have been moved to apps.tasks.admin
