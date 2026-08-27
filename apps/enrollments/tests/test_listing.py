from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.events.tests.helpers import create_verified_user

from .test_lifecycle import _future_event, cancel_url, enroll_url

ENROLLMENTS_URL = "/api/enrollments/"


class EnrollmentListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)
        self.other_seeker = create_verified_user(
            "other@example.com", Profile.Role.SEEKER
        )

        now = timezone.now()
        self.upcoming_event = _future_event(
            self.facilitator, title="Upcoming", starts_at=now + timedelta(days=5)
        )
        self.past_event = _future_event(
            self.facilitator,
            title="Past",
            starts_at=now - timedelta(days=5),
            ends_at=now - timedelta(days=5) + timedelta(hours=1),
        )

        self.client.force_authenticate(self.seeker)
        self.client.post(enroll_url(self.upcoming_event.id))
        self.client.post(enroll_url(self.past_event.id))

    def test_scope_required(self):
        response = self.client.get(ENROLLMENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_scope_rejected(self):
        response = self.client.get(ENROLLMENTS_URL, {"scope": "everything"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_scope_upcoming_returns_only_upcoming(self):
        response = self.client.get(ENROLLMENTS_URL, {"scope": "upcoming"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [row["event"]["title"] for row in response.data["results"]]
        self.assertEqual(titles, ["Upcoming"])

    def test_scope_past_returns_only_past(self):
        response = self.client.get(ENROLLMENTS_URL, {"scope": "past"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [row["event"]["title"] for row in response.data["results"]]
        self.assertEqual(titles, ["Past"])

    def test_canceled_enrollments_still_appear_as_history(self):
        self.client.post(cancel_url(self.upcoming_event.id))

        response = self.client.get(ENROLLMENTS_URL, {"scope": "upcoming"})
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "canceled")

    def test_only_returns_own_rows(self):
        self.client.force_authenticate(self.other_seeker)
        response = self.client.get(ENROLLMENTS_URL, {"scope": "upcoming"})
        self.assertEqual(response.data["results"], [])

    def test_facilitator_cannot_access(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.get(ENROLLMENTS_URL, {"scope": "upcoming"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access(self):
        self.client.force_authenticate(None)
        response = self.client.get(ENROLLMENTS_URL, {"scope": "upcoming"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
