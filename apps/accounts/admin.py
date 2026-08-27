from django.contrib import admin

from .models import EmailOTP, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_email_verified", "created_at")
    list_filter = ("role", "is_email_verified")
    search_fields = ("user__email",)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    # code_hash is a hash, not the plaintext code, but it's still shown
    # read-only: nothing should ever be able to edit OTP state by hand.
    list_display = ("user", "is_active", "attempts", "expires_at", "created_at", "consumed_at")
    list_filter = ("is_active",)
    search_fields = ("user__email",)
    readonly_fields = ("code_hash", "created_at")
