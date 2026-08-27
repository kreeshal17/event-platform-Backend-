from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.events.models import Event

from .helpers import create_verified_user

EVENTS_URL = "/api/events/"


def _create_event(facilitator, **overrides):
    now = timezone.now()
    starts_at = overrides.pop("starts_at", now + timedelta(days=7))
    ends_at = overrides.pop("ends_at", starts_at + timedelta(hours=2))
    defaults = {
        "title": "Untitled event",
        "description": "",
        "language": "en",
        "location": "Kathmandu",
    }
    defaults.update(overrides)
    return Event.objects.create(
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=facilitator,
        **defaults,
    )


class DiscoveryFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)
        self.client.force_authenticate(self.seeker)

    def _titles(self, response):
        return [row["title"] for row in response.data["results"]]

    def test_q_matches_title(self):
        _create_event(self.facilitator, title="Intro to Django")
        _create_event(self.facilitator, title="Advanced React")

        response = self.client.get(EVENTS_URL, {"q": "django"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._titles(response), ["Intro to Django"])

    def test_q_matches_description(self):
        _create_event(
            self.facilitator, title="Workshop A", description="Covers Django ORM"
        )
        _create_event(
            self.facilitator, title="Workshop B", description="Covers React hooks"
        )

        response = self.client.get(EVENTS_URL, {"q": "orm"})
        self.assertEqual(self._titles(response), ["Workshop A"])

    def test_q_no_match_returns_empty(self):
        _create_event(self.facilitator, title="Intro to Django")
        response = self.client.get(EVENTS_URL, {"q": "cobol"})
        self.assertEqual(response.data["count"], 0)

    def test_location_filter_is_exact(self):
        _create_event(self.facilitator, title="In KTM", location="Kathmandu")
        _create_event(self.facilitator, title="In Pokhara", location="Pokhara")

        response = self.client.get(EVENTS_URL, {"location": "Kathmandu"})
        self.assertEqual(self._titles(response), ["In KTM"])

    def test_location_filter_does_not_partial_match(self):
        _create_event(self.facilitator, title="In Kathmandu", location="Kathmandu")
        response = self.client.get(EVENTS_URL, {"location": "Kathman"})
        self.assertEqual(response.data["count"], 0)

    def test_language_filter_is_exact(self):
        _create_event(self.facilitator, title="English talk", language="en")
        _create_event(self.facilitator, title="Nepali talk", language="ne")

        response = self.client.get(EVENTS_URL, {"language": "ne"})
        self.assertEqual(self._titles(response), ["Nepali talk"])

    def test_starts_after_filter(self):
        now = timezone.now()
        _create_event(self.facilitator, title="Near", starts_at=now + timedelta(days=1))
        _create_event(self.facilitator, title="Far", starts_at=now + timedelta(days=30))

        response = self.client.get(
            EVENTS_URL, {"starts_after": (now + timedelta(days=10)).isoformat()}
        )
        self.assertEqual(self._titles(response), ["Far"])

    def test_starts_before_filter(self):
        now = timezone.now()
        _create_event(self.facilitator, title="Near", starts_at=now + timedelta(days=1))
        _create_event(self.facilitator, title="Far", starts_at=now + timedelta(days=30))

        response = self.client.get(
            EVENTS_URL, {"starts_before": (now + timedelta(days=10)).isoformat()}
        )
        self.assertEqual(self._titles(response), ["Near"])

    def test_starts_after_and_before_combine(self):
        now = timezone.now()
        _create_event(self.facilitator, title="Too soon", starts_at=now + timedelta(days=1))
        _create_event(self.facilitator, title="Just right", starts_at=now + timedelta(days=15))
        _create_event(self.facilitator, title="Too late", starts_at=now + timedelta(days=60))

        response = self.client.get(
            EVENTS_URL,
            {
                "starts_after": (now + timedelta(days=10)).isoformat(),
                "starts_before": (now + timedelta(days=20)).isoformat(),
            },
        )
        self.assertEqual(self._titles(response), ["Just right"])

    def test_filters_combine_with_and(self):
        _create_event(self.facilitator, title="Match", location="Kathmandu", language="en")
        _create_event(self.facilitator, title="Wrong language", location="Kathmandu", language="ne")
        _create_event(self.facilitator, title="Wrong location", location="Pokhara", language="en")

        response = self.client.get(
            EVENTS_URL, {"location": "Kathmandu", "language": "en"}
        )
        self.assertEqual(self._titles(response), ["Match"])

    def test_malformed_starts_after_returns_400(self):
        response = self.client.get(EVENTS_URL, {"starts_after": "not-a-date"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DiscoveryOrderingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)
        self.client.force_authenticate(self.seeker)

    def _titles(self, response):
        return [row["title"] for row in response.data["results"]]

    def test_upcoming_events_sort_before_past_events(self):
        now = timezone.now()
        _create_event(
            self.facilitator,
            title="Past event",
            starts_at=now - timedelta(days=5),
            ends_at=now - timedelta(days=5) + timedelta(hours=1),
        )
        _create_event(self.facilitator, title="Upcoming event", starts_at=now + timedelta(days=5))

        response = self.client.get(EVENTS_URL)
        self.assertEqual(self._titles(response), ["Upcoming event", "Past event"])

    def test_upcoming_events_are_soonest_first(self):
        now = timezone.now()
        _create_event(self.facilitator, title="Far upcoming", starts_at=now + timedelta(days=30))
        _create_event(self.facilitator, title="Near upcoming", starts_at=now + timedelta(days=1))

        response = self.client.get(EVENTS_URL)
        self.assertEqual(self._titles(response), ["Near upcoming", "Far upcoming"])

    def test_past_events_are_oldest_first(self):
        now = timezone.now()
        _create_event(
            self.facilitator,
            title="Recently past",
            starts_at=now - timedelta(days=1),
            ends_at=now - timedelta(days=1) + timedelta(hours=1),
        )
        _create_event(
            self.facilitator,
            title="Long past",
            starts_at=now - timedelta(days=30),
            ends_at=now - timedelta(days=30) + timedelta(hours=1),
        )

        response = self.client.get(EVENTS_URL)
        self.assertEqual(self._titles(response), ["Long past", "Recently past"])

    def test_full_ordering_upcoming_then_past_each_chronological(self):
        now = timezone.now()
        _create_event(self.facilitator, title="Upcoming far", starts_at=now + timedelta(days=30))
        _create_event(self.facilitator, title="Upcoming near", starts_at=now + timedelta(days=1))
        _create_event(
            self.facilitator,
            title="Past recent",
            starts_at=now - timedelta(days=1),
            ends_at=now - timedelta(days=1) + timedelta(hours=1),
        )
        _create_event(
            self.facilitator,
            title="Past old",
            starts_at=now - timedelta(days=30),
            ends_at=now - timedelta(days=30) + timedelta(hours=1),
        )

        response = self.client.get(EVENTS_URL)
        self.assertEqual(
            self._titles(response),
            ["Upcoming near", "Upcoming far", "Past old", "Past recent"],
        )


class DiscoveryPaginationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        self.seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)
        self.client.force_authenticate(self.seeker)

        now = timezone.now()
        for i in range(25):
            _create_event(
                self.facilitator,
                title=f"Event {i:02d}",
                starts_at=now + timedelta(days=i + 1),
            )

    def test_pagination_shape_and_page_size(self):
        response = self.client.get(EVENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data.keys()), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 25)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_second_page(self):
        response = self.client.get(EVENTS_URL, {"page": 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertIsNone(response.data["next"])
        self.assertIsNotNone(response.data["previous"])
