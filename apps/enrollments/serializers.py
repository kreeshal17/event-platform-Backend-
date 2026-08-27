from rest_framework import serializers

from apps.events.models import Event

from .models import Enrollment


class EventSummarySerializer(serializers.ModelSerializer):
    """Minimal event info nested in an enrollment — enough for a seeker
    to recognize which event this is without a second lookup.
    """

    class Meta:
        model = Event
        fields = ["id", "title", "location", "language", "starts_at", "ends_at"]


class EnrollmentSerializer(serializers.ModelSerializer):
    event = EventSummarySerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = ["id", "event", "status", "created_at", "updated_at", "canceled_at"]


class EnrollmentScopeSerializer(serializers.Serializer):
    """Validates GET /api/enrollments/?scope=upcoming|past."""

    scope = serializers.ChoiceField(choices=["upcoming", "past"])
