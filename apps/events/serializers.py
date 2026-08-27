from rest_framework import serializers

from .models import Event


class EventSerializer(serializers.ModelSerializer):
    """Used for list/retrieve/create/update on /api/events/.

    `seats_taken` is read-only here: it's a denormalized counter that only
    enrollment/cancellation (Phase 6/7) are allowed to move.
    """

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "language",
            "location",
            "starts_at",
            "ends_at",
            "capacity",
            "seats_taken",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "seats_taken", "created_by", "created_at", "updated_at"]

    def validate_capacity(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Must not be negative.")
        return value

    def validate(self, attrs):
        # Mirrors the event_ends_after_starts CheckConstraint at the
        # application layer, so a bad request gets a clean 400 instead of
        # an unhandled 500 from the database.
        starts_at = attrs.get(
            "starts_at", getattr(self.instance, "starts_at", None)
        )
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {"ends_at": "Must be after starts_at."}
            )
        return attrs


class FacilitatorEventSerializer(serializers.ModelSerializer):
    """Used for GET /api/facilitator/events/ — adds enrolled_count and
    available_seats. Both are derived from `seats_taken`, the denormalized
    counter on Event itself; no Enrollment model exists yet (Phase 6+).
    """

    enrolled_count = serializers.IntegerField(source="seats_taken", read_only=True)
    available_seats = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "language",
            "location",
            "starts_at",
            "ends_at",
            "capacity",
            "enrolled_count",
            "available_seats",
            "created_at",
            "updated_at",
        ]

    def get_available_seats(self, obj):
        if obj.capacity is None:
            return None
        return obj.capacity - obj.seats_taken
