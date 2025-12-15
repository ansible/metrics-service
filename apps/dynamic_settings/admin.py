"""
Admin configuration for dynamic_settings app.
"""

from django.contrib import admin

from .models import Setting


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    """Admin interface for Setting model."""

    list_display = ["setting_key", "last_modified_by", "modified"]
    list_filter = ["last_modified_by", "modified"]
    search_fields = ["setting_key"]
    readonly_fields = ["previous_value", "created", "modified"]
