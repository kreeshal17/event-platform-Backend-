from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, F, Q


class Event(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=100)
    location = models.CharField(max_length=255)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    # null = unlimited capacity. Plain (not Positive*) fields: the three
    # CheckConstraints below are the single, explicit source of truth for
    # what values are valid, rather than mixing them with Django's own
    # implicit PositiveIntegerField DB checks.
    capacity = models.IntegerField(null=True, blank=True)
    seats_taken = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["starts_at"], name="event_starts_at_idx"),
            models.Index(
                fields=["location", "starts_at"], name="event_location_starts_idx"
            ),
            models.Index(
                fields=["language", "starts_at"], name="event_language_starts_idx"
            ),
        ]
        constraints = [
            CheckConstraint(
                check=Q(ends_at__gt=F("starts_at")),
                name="event_ends_after_starts",
            ),
            CheckConstraint(
                check=Q(seats_taken__gte=0),
                name="event_seats_taken_non_negative",
            ),
            CheckConstraint(
                check=Q(capacity__isnull=True) | Q(seats_taken__lte=F("capacity")),
                name="event_seats_taken_le_capacity",
            ),
        ]

    def __str__(self):
        return self.title
