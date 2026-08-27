from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import Profile
from apps.common.management.commands.seed_demo import (
    ALL_DEMO_EMAILS,
    DEMO_PASSWORD,
)
from apps.enrollments.models import Enrollment
from apps.events.models import Event


class SeedDemoTests(TestCase):
    def _run(self):
        call_command("seed_demo", stdout=StringIO())

    def test_creates_expected_counts(self):
        self._run()

        self.assertEqual(
            User.objects.filter(
                profile__role=Profile.Role.FACILITATOR, email__in=ALL_DEMO_EMAILS
            ).count(),
            2,
        )
        seekers = User.objects.filter(
            profile__role=Profile.Role.SEEKER, email__in=ALL_DEMO_EMAILS
        )
        self.assertEqual(seekers.count(), 12)
        self.assertTrue(all(u.profile.is_email_verified for u in seekers))

        self.assertEqual(
            Event.objects.filter(created_by__email__in=ALL_DEMO_EMAILS).count(), 10
        )

    def test_seeded_facilitator_can_log_in(self):
        self._run()
        user = User.objects.get(email="facilitator1.demo@example.com")
        self.assertTrue(user.check_password(DEMO_PASSWORD))

    def test_concurrency_demo_event_has_nine_active_enrollments(self):
        self._run()
        event = Event.objects.get(title__startswith="Concurrency Demo")
        self.assertEqual(event.capacity, 10)
        self.assertEqual(event.seats_taken, 9)
        self.assertEqual(
            Enrollment.objects.filter(event=event, status=Enrollment.Status.ENROLLED).count(),
            9,
        )

    def test_lifecycle_demo_has_enroll_cancel_enroll_history(self):
        self._run()
        event = Event.objects.get(title__startswith="Lifecycle Demo")
        seeker = User.objects.get(email="seeker10.demo@example.com")

        rows = list(
            Enrollment.objects.filter(event=event, seeker=seeker).order_by("created_at")
        )
        self.assertEqual(len(rows), 2)
        older, newer = rows
        self.assertNotEqual(older.pk, newer.pk)
        self.assertEqual(older.status, Enrollment.Status.CANCELED)
        self.assertIsNotNone(older.canceled_at)
        self.assertEqual(newer.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(newer.canceled_at)

    def test_rerunning_is_safe_and_does_not_duplicate(self):
        self._run()
        self._run()

        self.assertEqual(
            User.objects.filter(email__in=ALL_DEMO_EMAILS).count(), len(ALL_DEMO_EMAILS)
        )
        self.assertEqual(
            Event.objects.filter(created_by__email__in=ALL_DEMO_EMAILS).count(), 10
        )
