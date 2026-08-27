from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.events.models import Event


class Enrollment(models.Model):
    class Status(models.TextChoices):
        ENROLLED = "enrolled", "Enrolled"
        CANCELED = "canceled", "Canceled"

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="enrollments"
    )
    seeker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ENROLLED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["event", "status"], name="enrollment_event_status_idx"
            ),
            models.Index(
                fields=["seeker", "status"], name="enrollment_seeker_status_idx"
            ),
        ]
        constraints = [
            # Many canceled historical rows are allowed; at most one
            # ACTIVE (status=enrolled) row per (event, seeker) at a time.
            # A plain unique_together would make re-enrollment after a
            # cancellation impossible without deleting history.
            models.UniqueConstraint(
                fields=["event", "seeker"],
                condition=Q(status="enrolled"),
                name="uniq_active_enrollment",
            ),
        ]

    def __str__(self):
        return f"Enrollment(event_id={self.event_id}, seeker_id={self.seeker_id}, status={self.status})"
