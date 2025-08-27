"""
Admin configuration for core models.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Animal,
    Organization,
    Task,
    TaskChain,
    TaskChainMembership,
    TaskDependency,
    TaskExecution,
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


class TaskExecutionInline(admin.TabularInline):
    """Inline admin for TaskExecution."""

    model = TaskExecution
    extra = 0
    readonly_fields = ("started_at", "completed_at", "execution_time_seconds")
    fields = ("status", "worker_id", "started_at", "completed_at", "execution_time_seconds", "error_message")


class TaskDependencyInline(admin.TabularInline):
    """Inline admin for TaskDependency."""

    model = TaskDependency
    fk_name = "dependent_task"
    extra = 0
    fields = ("prerequisite_task", "required_status")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """Admin for Task model."""

    list_display = (
        "name",
        "function_name",
        "status_colored",
        "priority",
        "scheduled_time",
        "attempts",
        "created_by",
        "created",
    )
    list_filter = ("status", "priority", "is_recurring", "function_name", "created_by")
    search_fields = ("name", "description", "function_name")
    readonly_fields = ("started_at", "completed_at", "attempts")

    fieldsets = (
        ("Basic Information", {"fields": ("name", "description", "function_name", "created_by")}),
        ("Task Data", {"fields": ("task_data",), "classes": ("collapse",)}),
        ("Scheduling", {"fields": ("scheduled_time", "cron_expression", "is_recurring", "priority")}),
        ("Execution Settings", {"fields": ("max_attempts", "timeout_seconds")}),
        (
            "Status & Results",
            {
                "fields": ("status", "attempts", "started_at", "completed_at", "result_data", "error_message"),
                "classes": ("collapse",),
            },
        ),
    )

    inlines = [TaskDependencyInline, TaskExecutionInline]

    actions = ["cancel_tasks", "retry_tasks", "reset_tasks"]

    def status_colored(self, obj):
        """Display status with color coding."""
        colors = {
            "pending": "orange",
            "running": "blue",
            "completed": "green",
            "failed": "red",
            "cancelled": "gray",
            "waiting_for_dependencies": "purple",
        }
        color = colors.get(obj.status, "black")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_colored.short_description = "Status"

    def cancel_tasks(self, request, queryset):
        """Admin action to cancel selected tasks."""
        updated = queryset.filter(status__in=["pending", "running", "waiting_for_dependencies"]).update(
            status="cancelled"
        )
        self.message_user(request, f"Cancelled {updated} task(s).")

    cancel_tasks.short_description = "Cancel selected tasks"

    def retry_tasks(self, request, queryset):
        """Admin action to retry failed tasks."""
        count = 0
        for task in queryset.filter(status="failed"):
            if task.can_retry():
                task.status = "pending"
                task.error_message = ""
                task.started_at = None
                task.completed_at = None
                task.save()
                count += 1
        self.message_user(request, f"Reset {count} task(s) for retry.")

    retry_tasks.short_description = "Retry failed tasks"

    def reset_tasks(self, request, queryset):
        """Admin action to reset tasks to pending."""
        updated = queryset.exclude(status="running").update(
            status="pending", error_message="", started_at=None, completed_at=None, result_data={}
        )
        self.message_user(request, f"Reset {updated} task(s) to pending.")

    reset_tasks.short_description = "Reset tasks to pending"


@admin.register(TaskDependency)
class TaskDependencyAdmin(admin.ModelAdmin):
    """Admin for TaskDependency model."""

    list_display = ("dependent_task", "prerequisite_task", "required_status", "created")
    list_filter = ("required_status",)
    search_fields = (
        "dependent_task__name",
        "prerequisite_task__name",
        "dependent_task__function_name",
        "prerequisite_task__function_name",
    )
    autocomplete_fields = ("dependent_task", "prerequisite_task")


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    """Admin for TaskExecution model."""

    list_display = ("task", "status", "worker_id", "started_at", "execution_time_seconds", "error_message_short")
    list_filter = ("status", "started_at")
    search_fields = ("task__name", "worker_id", "error_message")
    readonly_fields = ("started_at", "completed_at", "execution_time_seconds")

    def error_message_short(self, obj):
        """Display shortened error message."""
        if obj.error_message:
            return obj.error_message[:50] + "..." if len(obj.error_message) > 50 else obj.error_message
        return "-"

    error_message_short.short_description = "Error"


class TaskChainMembershipInline(admin.TabularInline):
    """Inline admin for TaskChainMembership."""

    model = TaskChainMembership
    extra = 0
    fields = ("task", "order")
    ordering = ("order",)


@admin.register(TaskChain)
class TaskChainAdmin(admin.ModelAdmin):
    """Admin for TaskChain model."""

    list_display = ("name", "is_active", "task_count", "created_by", "created")
    list_filter = ("is_active", "created_by")
    search_fields = ("name", "description")

    inlines = [TaskChainMembershipInline]

    def task_count(self, obj):
        """Display number of tasks in chain."""
        return obj.tasks.count()

    task_count.short_description = "Tasks"


@admin.register(TaskChainMembership)
class TaskChainMembershipAdmin(admin.ModelAdmin):
    """Admin for TaskChainMembership model."""

    list_display = ("chain", "task", "order", "created")
    list_filter = ("chain",)
    search_fields = ("chain__name", "task__name")
    ordering = ("chain", "order")
