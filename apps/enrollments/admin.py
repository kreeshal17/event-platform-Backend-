from django.contrib import admin

from .models import Enrollment


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("event", "seeker", "status", "created_at", "canceled_at")
    list_filter = ("status",)
    search_fields = ("event__title", "seeker__email")
    readonly_fields = ("created_at", "updated_at")
