"""Challenge B — re-enrollment lifecycle.

Written and run FIRST, against no enroll/cancel endpoints at all (RED),
per AGENT_SPEC.md rule 8. Every assertion here is the CORRECT required
behaviour — none of it is tuned to match a buggy implementation.
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


def _future_event(facilitator, **overrides):
    now = timezone.now()
    starts_at = overrides.pop("starts_at", now + timedelta(days=7))
    ends_at = overrides.pop("ends_at", starts_at + timedelta(hours=2))
    defaults = {
        "title": "Workshop",
        "description": "",
        "language": "en",
        "location": "Kathmandu",
        "capacity": 10,
    }
    defaults.update(overrides)
    return Event.objects.create(
        starts_at=starts_at, ends_at=ends_at, created_by=facilitator, **defaults
    )


def enroll_url(event_id):
    return f"/api/events/{event_id}/enroll/"


def cancel_url(event_id):
    return f"/api/events/{event_id}/cancel/"


class ReEnrollmentLifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)
        self.event = _future_event(self.facilitator)
        self.client.force_authenticate(self.seeker)

    def test_enroll_cancel_enroll_creates_new_row_not_revived_old_one(self):
        first = self.client.post(enroll_url(self.event.id))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        cancel = self.client.post(cancel_url(self.event.id))
        self.assertEqual(cancel.status_code, status.HTTP_200_OK)

        second = self.client.post(enroll_url(self.event.id))
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

        rows = list(
            Enrollment.objects.filter(event=self.event, seeker=self.seeker).order_by(
                "created_at"
            )
        )
        self.assertEqual(len(rows), 2)

        older, newer = rows
        self.assertNotEqual(older.pk, newer.pk)

        self.assertEqual(older.status, Enrollment.Status.CANCELED)
        self.assertIsNotNone(older.canceled_at)

        self.assertEqual(newer.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(newer.canceled_at)

    def test_enroll_while_already_active_returns_409_already_enrolled(self):
        first = self.client.post(enroll_url(self.event.id))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(enroll_url(self.event.id))
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "already_enrolled")

        # Still only one active row — the failed attempt created nothing.
        self.assertEqual(
            Enrollment.objects.filter(
                event=self.event, seeker=self.seeker, status=Enrollment.Status.ENROLLED
            ).count(),
            1,
        )

    def test_cancel_with_no_active_enrollment_returns_404(self):
        response = self.client.post(cancel_url(self.event.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "no_active_enrollment")
