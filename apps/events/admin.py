from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "created_by",
        "language",
        "location",
        "starts_at",
        "ends_at",
        "capacity",
        "seats_taken",
    )
    list_filter = ("language", "location")
    search_fields = ("title", "description", "location")
    readonly_fields = ("seats_taken", "created_at", "updated_at")
