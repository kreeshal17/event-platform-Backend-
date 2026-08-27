"""Challenge A — concurrency.

Written and run FIRST against the naive Phase 6 enroll (RED), per
AGENT_SPEC.md rule 8. Uses TransactionTestCase (not TestCase): TestCase
wraps each test in a single transaction on a single connection, so
concurrent threads never truly contend and this would pass vacuously.

Every assertion here is the CORRECT required invariant, in the required
order — none of it is tuned to match whatever numbers the naive
implementation happens to produce. Do not add "5 successes" or similar
broken-numbers assertions here; the actual observed numbers from the red
run belong in the phase report / DEBUGGING.md, not in this file.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.enrollments.models import Enrollment
from apps.events.models import Event
from apps.events.tests.helpers import create_verified_user

WORKER_COUNT = 5


def _concurrent_enroll(event_id: int, seeker_id: int):
    """Runs in a worker thread: closes whatever connection this thread
    inherited so it opens its own fresh one, per spec. Also closes it
    again afterward — a raw ThreadPoolExecutor thread has no
    request_finished signal to do that automatically, and leaving
    connections open leaks Postgres sessions that then block the test
    database from being torn down at the end of the run.
    """
    connection.close()
    try:
        seeker = User.objects.get(pk=seeker_id)
        client = APIClient()
        client.force_authenticate(seeker)
        response = client.post(f"/api/events/{event_id}/enroll/")
        return response.status_code, getattr(response, "data", None)
    finally:
        connection.close()


class ConcurrentEnrollmentTests(TransactionTestCase):
    def test_exactly_one_of_five_concurrent_enrolls_succeeds_on_the_last_seat(self):
        facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        now = timezone.now()
        event = Event.objects.create(
            title="Concurrency Demo",
            language="en",
            location="Kathmandu",
            starts_at=now + timedelta(days=7),
            ends_at=now + timedelta(days=7, hours=2),
            capacity=10,
            seats_taken=9,
            created_by=facilitator,
        )

        # Nine REAL active Enrollment rows for nine distinct seekers — the
        # naive implementation counts rows, the final implementation reads
        # the counter, so both need to already agree going in.
        existing_seekers = [
            create_verified_user(f"existing{i}@example.com", Profile.Role.SEEKER)
            for i in range(9)
        ]
        for seeker in existing_seekers:
            Enrollment.objects.create(
                event=event, seeker=seeker, status=Enrollment.Status.ENROLLED
            )

        contenders = [
            create_verified_user(f"contender{i}@example.com", Profile.Role.SEEKER)
            for i in range(WORKER_COUNT)
        ]

        with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
            futures = [
                executor.submit(_concurrent_enroll, event.id, seeker.id)
                for seeker in contenders
            ]
            results = [future.result() for future in futures]

        successes = [r for r in results if r[0] == 201]
        failures = [r for r in results if r[0] == 409]

        # 1. Exactly one of the five responses is 201.
        self.assertEqual(len(successes), 1, f"results were: {results}")

        # 2. The other four are 409 with code event_full.
        self.assertEqual(len(failures), 4, f"results were: {results}")
        for status_code, data in failures:
            self.assertEqual(data["code"], "event_full")

        # 3. The active enrollment count for the event never exceeds 10.
        active_count = Enrollment.objects.filter(
            event=event, status=Enrollment.Status.ENROLLED
        ).count()
        self.assertEqual(active_count, 10)

        # 4. seats_taken ends at 10. (Last, per spec — the meaningful
        # signal is assertion 1/3, not this one.)
        event.refresh_from_db()
        self.assertEqual(event.seats_taken, 10)
