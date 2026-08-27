"""Query-parameter filtering/ordering for GET /api/events/.

Kept separate from the view so the filtering/ordering logic is testable on
its own, independent of the HTTP layer.
"""

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.db.models.functions import Now
from rest_framework import serializers


class EventFilterSerializer(serializers.Serializer):
    """Validates GET /api/events/ query params. Used purely for input
    validation/parsing (e.g. starts_after/starts_before into real
    datetimes with a clean 400 on a malformed value) — not a model
    serializer.
    """

    q = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    language = serializers.CharField(required=False, allow_blank=True)
    starts_after = serializers.DateTimeField(required=False)
    starts_before = serializers.DateTimeField(required=False)


def filter_events(queryset: QuerySet, filters: dict) -> QuerySet:
    """`filters` is EventFilterSerializer.validated_data (or any dict with
    the same keys/types).
    """
    q = filters.get("q")
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q) | Q(description__icontains=q)
        )

    location = filters.get("location")
    if location:
        queryset = queryset.filter(location=location)

    language = filters.get("language")
    if language:
        queryset = queryset.filter(language=language)

    starts_after = filters.get("starts_after")
    if starts_after:
        queryset = queryset.filter(starts_at__gt=starts_after)

    starts_before = filters.get("starts_before")
    if starts_before:
        queryset = queryset.filter(starts_at__lt=starts_before)

    return queryset


def order_upcoming_first(queryset: QuerySet) -> QuerySet:
    """ORDER BY (starts_at < now()) ASC, starts_at ASC, per spec: events
    that haven't started yet sort first (soonest first), then events
    already underway/finished (oldest first among those).
    """
    return queryset.annotate(
        _is_past=Case(
            When(starts_at__lt=Now(), then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).order_by("_is_past", "starts_at")
