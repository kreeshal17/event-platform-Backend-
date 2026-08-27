from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Profile
from apps.events.models import Event

from .helpers import create_verified_user


class EventConstraintTests(TestCase):
    """Bypasses the serializer entirely to prove these are real database
    constraints, not just application-level validation — mirrors the
    pattern used for the LOWER(email) index in apps.accounts.
    """

    def setUp(self):
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.starts_at = timezone.now() + timedelta(days=7)
        self.ends_at = self.starts_at + timedelta(hours=2)

    def _base_kwargs(self, **overrides):
        kwargs = {
            "title": "Constraint check",
            "language": "en",
            "location": "Kathmandu",
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "created_by": self.facilitator,
        }
        kwargs.update(overrides)
        return kwargs

    def test_ends_at_not_after_starts_at_violates_db_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Event.objects.create(
                    **self._base_kwargs(ends_at=self.starts_at - timedelta(hours=1))
                )

    def test_ends_at_equal_to_starts_at_violates_db_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Event.objects.create(**self._base_kwargs(ends_at=self.starts_at))

    def test_negative_seats_taken_violates_db_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Event.objects.create(**self._base_kwargs(seats_taken=-1))

    def test_seats_taken_exceeding_capacity_violates_db_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Event.objects.create(
                    **self._base_kwargs(capacity=5, seats_taken=6)
                )

    def test_seats_taken_equal_to_capacity_is_allowed(self):
        event = Event.objects.create(**self._base_kwargs(capacity=5, seats_taken=5))
        self.assertEqual(event.seats_taken, 5)

    def test_null_capacity_allows_any_non_negative_seats_taken(self):
        event = Event.objects.create(
            **self._base_kwargs(capacity=None, seats_taken=1000)
        )
        self.assertEqual(event.seats_taken, 1000)
