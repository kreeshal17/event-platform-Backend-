from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.events.models import Event

from .helpers import create_verified_user

FACILITATOR_EVENTS_URL = "/api/facilitator/events/"


class FacilitatorEventListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.other_facilitator = create_verified_user(
            "other.facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)

        starts_at = timezone.now() + timedelta(days=7)
        ends_at = starts_at + timedelta(hours=2)

        self.own_event = Event.objects.create(
            title="Own event",
            language="en",
            location="Kathmandu",
            starts_at=starts_at,
            ends_at=ends_at,
            capacity=10,
            seats_taken=3,
            created_by=self.facilitator,
        )
        self.unlimited_event = Event.objects.create(
            title="Unlimited event",
            language="en",
            location="Pokhara",
            starts_at=starts_at,
            ends_at=ends_at,
            capacity=None,
            seats_taken=5,
            created_by=self.facilitator,
        )
        Event.objects.create(
            title="Someone else's event",
            language="en",
            location="Lalitpur",
            starts_at=starts_at,
            ends_at=ends_at,
            capacity=10,
            seats_taken=0,
            created_by=self.other_facilitator,
        )

    def test_facilitator_sees_only_own_events(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.get(FACILITATOR_EVENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        titles = {row["title"] for row in response.data["results"]}
        self.assertEqual(titles, {"Own event", "Unlimited event"})

    def test_seeker_cannot_access_facilitator_events(self):
        self.client.force_authenticate(self.seeker)
        response = self.client.get(FACILITATOR_EVENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access_facilitator_events(self):
        response = self.client.get(FACILITATOR_EVENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_enrolled_count_and_available_seats_reflect_seats_taken(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.get(FACILITATOR_EVENTS_URL)

        by_title = {row["title"]: row for row in response.data["results"]}
        capped = by_title["Own event"]
        self.assertEqual(capped["enrolled_count"], 3)
        self.assertEqual(capped["available_seats"], 7)  # 10 - 3

    def test_available_seats_is_null_for_unlimited_capacity(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.get(FACILITATOR_EVENTS_URL)

        by_title = {row["title"]: row for row in response.data["results"]}
        unlimited = by_title["Unlimited event"]
        self.assertEqual(unlimited["enrolled_count"], 5)
        self.assertIsNone(unlimited["available_seats"])
