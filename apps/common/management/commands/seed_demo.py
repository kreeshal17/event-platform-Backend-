"""python manage.py seed_demo

Creates demo data: 2 facilitators, 12 seekers (all verified), ~10 events
spanning past and upcoming with mixed languages/locations, one
capacity=10 event with nine active enrollments (seats_taken=9) ready for
a manual concurrency demo, and one seeker with a completed
enroll -> cancel -> enroll history.

Safe to re-run: deletes any previously seeded demo users first (matched
by the exact, fixed emails this command always uses), cascading to their
Profiles/Events/Enrollments, then recreates everything from scratch.

Demo credentials are documented in README.md. DEMO_PASSWORD below is a
fixed, published, development-only password for locally seeded accounts
— not a real secret, and not usable against anything but a database this
command was run against.
"""

import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Profile
from apps.enrollments.services import cancel_enrollment, enroll_seeker
from apps.events.models import Event

DEMO_PASSWORD = "DemoPass123!"

FACILITATOR_EMAILS = [
    "facilitator1.demo@example.com",
    "facilitator2.demo@example.com",
]
SEEKER_EMAILS = [f"seeker{i}.demo@example.com" for i in range(1, 13)]
ALL_DEMO_EMAILS = FACILITATOR_EMAILS + SEEKER_EMAILS

# (title, language, location, starts_in_days, duration_hours, capacity)
# starts_in_days negative = already happened (past), positive = upcoming.
# facilitator_index selects which of the 2 created facilitators owns it.
EVENT_SPECS = [
    ("Intro to Django REST Framework", "en", "Kathmandu", 3, 2, 30, 0),
    ("Advanced PostgreSQL Indexing", "en", "Pokhara", 10, 3, 20, 1),
    ("Nepali Sign Language Basics", "ne", "Lalitpur", 15, 2, None, 0),
    ("Intro to React Hooks", "en", "Kathmandu", -5, 2, 25, 1),
    ("Data Structures Refresher", "en", "Biratnagar", -20, 3, None, 0),
    ("Hindi Conversation Circle", "hi", "Kathmandu", 7, 1, 15, 1),
    ("Concurrency Demo: Almost Full Workshop", "en", "Kathmandu", 5, 2, 10, 0),
    ("Lifecycle Demo: Weekend Photography Walk", "en", "Pokhara", 8, 4, 12, 1),
    ("Spanish for Travelers", "es", "Lalitpur", 30, 2, 20, 0),
    ("Retro: Community Meetup Highlights", "en", "Kathmandu", -45, 2, None, 1),
]


class Command(BaseCommand):
    help = "Seeds demo data: facilitators, seekers, events, and enrollments."

    def handle(self, *args, **options):
        with transaction.atomic():
            self._delete_existing_demo_data()

            facilitators = [
                self._create_user(email, Profile.Role.FACILITATOR)
                for email in FACILITATOR_EMAILS
            ]
            seekers = [
                self._create_user(email, Profile.Role.SEEKER)
                for email in SEEKER_EMAILS
            ]

            events = self._create_events(facilitators)
            concurrency_event = next(
                e for e in events if e.title.startswith("Concurrency Demo")
            )
            lifecycle_event = next(
                e for e in events if e.title.startswith("Lifecycle Demo")
            )

            # Nine active enrollments on the capacity=10 concurrency-demo
            # event — one seat left, ready for a manual "several seekers
            # race for the last seat" demo (see README).
            for seeker in seekers[:9]:
                enroll_seeker(concurrency_event, seeker)

            # One seeker with a completed enroll -> cancel -> enroll
            # history (the Challenge B lifecycle), on a *different* event
            # so it doesn't disturb the concurrency-demo event's exact
            # seat count above.
            lifecycle_seeker = seekers[9]
            enroll_seeker(lifecycle_event, lifecycle_seeker)
            cancel_enrollment(lifecycle_event, lifecycle_seeker)
            enroll_seeker(lifecycle_event, lifecycle_seeker)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(facilitators)} facilitators, {len(seekers)} seekers, "
                f"{len(events)} events."
            )
        )
        concurrency_event.refresh_from_db()
        self.stdout.write(
            f"Concurrency demo: '{concurrency_event.title}' (id={concurrency_event.id}) "
            f"has {concurrency_event.capacity - concurrency_event.seats_taken} seat(s) "
            "left — POST /api/events/{id}/enroll/ concurrently as several seekers to "
            "see it enforced correctly."
        )
        self.stdout.write(
            f"Lifecycle demo: seeker '{lifecycle_seeker.email}' has an "
            f"enroll->cancel->enroll history on '{lifecycle_event.title}' "
            f"(id={lifecycle_event.id})."
        )
        self.stdout.write(
            f"All demo accounts use the password: {DEMO_PASSWORD} "
            "(see README for the full credential list)."
        )

    def _delete_existing_demo_data(self):
        deleted, _ = User.objects.filter(email__in=ALL_DEMO_EMAILS).delete()
        if deleted:
            self.stdout.write(
                f"Removed {deleted} existing demo-related objects before reseeding."
            )

    def _create_user(self, email: str, role: str) -> User:
        user = User.objects.create_user(
            username=uuid.uuid4().hex, email=email, password=DEMO_PASSWORD
        )
        Profile.objects.create(user=user, role=role, is_email_verified=True)
        return user

    def _create_events(self, facilitators: list[User]) -> list[Event]:
        now = timezone.now()
        events = []
        for (
            title,
            language,
            location,
            starts_in_days,
            duration_hours,
            capacity,
            facilitator_index,
        ) in EVENT_SPECS:
            starts_at = now + timedelta(days=starts_in_days)
            ends_at = starts_at + timedelta(hours=duration_hours)
            events.append(
                Event.objects.create(
                    title=title,
                    description=f"Demo event: {title}.",
                    language=language,
                    location=location,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    capacity=capacity,
                    created_by=facilitators[facilitator_index],
                )
            )
        return events
