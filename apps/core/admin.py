"""
Django admin configuration for core models.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Animal, Organization, Team, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for User model."""

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "date_joined",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Additional Info",
            {
                "fields": ("resource",),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("resource", "date_joined", "last_login")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin configuration for Organization model."""

    list_display = ("name", "description", "created", "modified")
    list_filter = ("created", "modified")
    search_fields = ("name", "description")
    filter_horizontal = ("users", "admins")
    readonly_fields = ("resource", "created", "modified")

    fieldsets = (
        (None, {"fields": ("name", "description", "extra_field")}),
        (
            "Users",
            {
                "fields": ("users", "admins"),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("resource", "created", "modified"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Admin configuration for Team model."""

    list_display = ("name", "organization", "description", "created", "modified")
    list_filter = ("organization", "created", "modified")
    search_fields = ("name", "description", "organization__name")
    filter_horizontal = ("users", "admins", "team_parents")
    readonly_fields = ("resource", "created", "modified")

    fieldsets = (
        (None, {"fields": ("name", "organization", "description")}),
        (
            "Hierarchy",
            {
                "fields": ("team_parents",),
            },
        ),
        (
            "Users",
            {
                "fields": ("users", "admins"),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("resource", "created", "modified"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    """Admin configuration for Animal model."""

    list_display = ("name", "kind", "owner", "age", "created", "modified")
    list_filter = ("kind", "age", "created", "modified")
    search_fields = ("name", "owner__username", "owner__first_name", "owner__last_name")
    filter_horizontal = ("people_friends",)
    readonly_fields = ("created", "modified")

    fieldsets = (
        (None, {"fields": ("name", "kind", "owner", "age", "description")}),
        (
            "Relationships",
            {
                "fields": ("people_friends",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created", "modified"),
                "classes": ("collapse",),
            },
        ),
    )
