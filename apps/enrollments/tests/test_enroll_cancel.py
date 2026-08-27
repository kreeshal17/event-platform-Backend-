"""Enroll/cancel behaviour beyond Challenge B's core lifecycle assertions:
capacity, permissions, and response shape.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.enrollments.models import Enrollment
from apps.events.models import Event
from apps.events.tests.helpers import create_verified_user

from .test_lifecycle import _future_event, cancel_url, enroll_url


class EnrollCapacityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )

    def test_event_full_returns_409_with_exact_spec_body(self):
        event = _future_event(self.facilitator, capacity=1)
        first_seeker = create_verified_user("first@example.com", Profile.Role.SEEKER)
        second_seeker = create_verified_user("second@example.com", Profile.Role.SEEKER)

        self.client.force_authenticate(first_seeker)
        first = self.client.post(enroll_url(event.id))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(second_seeker)
        second = self.client.post(enroll_url(event.id))
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data, {"detail": "Event is full", "code": "event_full"})

    def test_unlimited_capacity_never_reports_full(self):
        event = _future_event(self.facilitator, capacity=None)
        for i in range(5):
            seeker = create_verified_user(f"seeker{i}@example.com", Profile.Role.SEEKER)
            self.client.force_authenticate(seeker)
            response = self.client.post(enroll_url(event.id))
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_a_canceled_seat_frees_capacity_for_someone_else(self):
        event = _future_event(self.facilitator, capacity=1)
        first_seeker = create_verified_user("first@example.com", Profile.Role.SEEKER)
        second_seeker = create_verified_user("second@example.com", Profile.Role.SEEKER)

        self.client.force_authenticate(first_seeker)
        self.client.post(enroll_url(event.id))
        self.client.post(cancel_url(event.id))

        self.client.force_authenticate(second_seeker)
        response = self.client.post(enroll_url(event.id))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class EnrollCancelPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.event = _future_event(self.facilitator)

    def test_facilitator_cannot_enroll(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.post(enroll_url(self.event.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_enroll(self):
        response = self.client.post(enroll_url(self.event.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_enroll_in_nonexistent_event_returns_404(self):
        seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)
        self.client.force_authenticate(seeker)
        response = self.client.post(enroll_url(999999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_seeker_cannot_cancel_another_seekers_enrollment_by_reusing_their_own_call(
        self,
    ):
        # There is no seeker/enrollment id in the request at all — cancel
        # only ever targets the CALLER's own active enrollment for this
        # event, so there's no way to target someone else's by construction.
        seeker_a = create_verified_user("a@example.com", Profile.Role.SEEKER)
        seeker_b = create_verified_user("b@example.com", Profile.Role.SEEKER)

        self.client.force_authenticate(seeker_a)
        self.client.post(enroll_url(self.event.id))

        self.client.force_authenticate(seeker_b)
        response = self.client.post(cancel_url(self.event.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "no_active_enrollment")

        # seeker_a's enrollment is untouched.
        self.assertEqual(
            Enrollment.objects.get(event=self.event, seeker=seeker_a).status,
            Enrollment.Status.ENROLLED,
        )
