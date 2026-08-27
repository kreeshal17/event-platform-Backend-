from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Application-specific data for a User: role and verification state.

    Kept as a separate model (rather than a custom User) so the default
    django.contrib.auth.models.User stays untouched, per spec.
    """

    class Role(models.TextChoices):
        SEEKER = "seeker", "Seeker"
        FACILITATOR = "facilitator", "Facilitator"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    is_email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} ({self.role})"


class EmailOTP(models.Model):
    """A single issued OTP. Only the HMAC hash of the code is ever stored."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_otps",
    )
    code_hash = models.CharField(max_length=64)  # hex HMAC-SHA256 digest
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"EmailOTP(user_id={self.user_id}, active={self.is_active})"
