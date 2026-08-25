from django.contrib import admin

from apps.service_ingest.models import ExternalEvent, ServiceDefinition


@admin.register(ServiceDefinition)
class ServiceDefinitionAdmin(admin.ModelAdmin):
    list_display = ["service_name", "event_name", "display_name", "version", "active", "registered_at", "last_seen_at"]
    list_filter = ["service_name", "active"]
    search_fields = ["service_name", "event_name", "display_name"]
    readonly_fields = ["registered_at", "last_seen_at"]


@admin.register(ExternalEvent)
class ExternalEventAdmin(admin.ModelAdmin):
    list_display = ["id", "service", "payload_type", "status", "created", "sent_at", "retry_count"]
    list_filter = ["status", "payload_type", "service"]
    search_fields = ["service__service_name"]
    readonly_fields = ["created", "modified", "segment_anonymous_id", "sent_at"]
    raw_id_fields = ["service"]
