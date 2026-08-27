from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.events.models import Event

from .helpers import create_verified_user

EVENTS_URL = "/api/events/"


def event_detail_url(pk):
    return f"/api/events/{pk}/"


def _payload(**overrides):
    starts_at = timezone.now() + timedelta(days=7)
    ends_at = starts_at + timedelta(hours=2)
    payload = {
        "title": "Intro to Django",
        "description": "A hands-on workshop.",
        "language": "en",
        "location": "Kathmandu",
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "capacity": 10,
    }
    payload.update(overrides)
    return payload


class EventCreateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)

    def test_facilitator_can_create_event(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.post(EVENTS_URL, _payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        event = Event.objects.get(pk=response.data["id"])
        self.assertEqual(event.created_by, self.facilitator)
        self.assertEqual(event.seats_taken, 0)

    def test_seeker_cannot_create_event(self):
        self.client.force_authenticate(self.seeker)
        response = self.client.post(EVENTS_URL, _payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Event.objects.exists())

    def test_unauthenticated_cannot_create_event(self):
        response = self.client.post(EVENTS_URL, _payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_created_by_and_seats_taken_are_not_client_settable(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.post(
            EVENTS_URL,
            _payload(created_by=self.seeker.id, seats_taken=999),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(pk=response.data["id"])
        self.assertEqual(event.created_by, self.facilitator)
        self.assertEqual(event.seats_taken, 0)

    def test_ends_at_before_starts_at_rejected(self):
        self.client.force_authenticate(self.facilitator)
        starts_at = timezone.now() + timedelta(days=7)
        response = self.client.post(
            EVENTS_URL,
            _payload(
                starts_at=starts_at.isoformat(),
                ends_at=(starts_at - timedelta(hours=1)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Event.objects.exists())

    def test_negative_capacity_rejected(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.post(EVENTS_URL, _payload(capacity=-1), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_null_capacity_means_unlimited(self):
        self.client.force_authenticate(self.facilitator)
        response = self.client.post(EVENTS_URL, _payload(capacity=None), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["capacity"])


class EventReadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)
        self.client.force_authenticate(self.facilitator)
        response = self.client.post(EVENTS_URL, _payload(), format="json")
        self.event_id = response.data["id"]

    def test_seeker_can_list_events(self):
        self.client.force_authenticate(self.seeker)
        response = self.client.get(EVENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_seeker_can_retrieve_event(self):
        self.client.force_authenticate(self.seeker)
        response = self.client.get(event_detail_url(self.event_id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.event_id)

    def test_unauthenticated_cannot_list_events(self):
        self.client.force_authenticate(None)
        response = self.client.get(EVENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EventUpdateDeleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = create_verified_user("owner@example.com", Profile.Role.FACILITATOR)
        self.other_facilitator = create_verified_user(
            "other.facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)

        self.client.force_authenticate(self.owner)
        response = self.client.post(EVENTS_URL, _payload(), format="json")
        self.event_id = response.data["id"]

    def test_owner_can_patch_own_event(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            event_detail_url(self.event_id), {"title": "Updated title"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Updated title")

    def test_non_owner_facilitator_cannot_patch(self):
        self.client.force_authenticate(self.other_facilitator)
        response = self.client.patch(
            event_detail_url(self.event_id), {"title": "Hijacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_seeker_cannot_patch(self):
        self.client.force_authenticate(self.seeker)
        response = self.client.patch(
            event_detail_url(self.event_id), {"title": "Hijacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_cannot_move_seats_taken_or_created_by(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            event_detail_url(self.event_id),
            {"seats_taken": 999, "created_by": self.seeker.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = Event.objects.get(pk=self.event_id)
        self.assertEqual(event.seats_taken, 0)
        self.assertEqual(event.created_by, self.owner)

    def test_put_not_allowed(self):
        self.client.force_authenticate(self.owner)
        response = self.client.put(
            event_detail_url(self.event_id), _payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_owner_can_delete_own_event(self):
        self.client.force_authenticate(self.owner)
        response = self.client.delete(event_detail_url(self.event_id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Event.objects.filter(pk=self.event_id).exists())

    def test_non_owner_facilitator_cannot_delete(self):
        self.client.force_authenticate(self.other_facilitator)
        response = self.client.delete(event_detail_url(self.event_id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Event.objects.filter(pk=self.event_id).exists())

    def test_seeker_cannot_delete(self):
        self.client.force_authenticate(self.seeker)
        response = self.client.delete(event_detail_url(self.event_id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
