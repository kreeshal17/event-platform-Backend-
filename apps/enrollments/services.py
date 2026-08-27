"""Enrollment business logic.

Final (Phase 7) implementation: enroll and cancel both take a row lock on
the Event via select_for_update() inside transaction.atomic(), so the
whole check-then-act sequence (and the seats_taken update) is serialized
per event. This replaces the Phase 6 naive version, which counted active
Enrollment rows with no lock and never touched seats_taken — see
DEBUGGING.md and apps/enrollments/tests/test_concurrency.py (Challenge A)
for the race that left observable and the fix here.

The seats_taken <= capacity and seats_taken >= 0 CheckConstraints on Event
remain as a database-level backstop regardless of this locking.
"""

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.common.exceptions import AlreadyEnrolled, EventFull, NoActiveEnrollment
from apps.events.models import Event

from .models import Enrollment


def enroll_seeker(event: Event, seeker: User) -> Enrollment:
    with transaction.atomic():
        locked_event = Event.objects.select_for_update().get(pk=event.pk)

        if Enrollment.objects.filter(
            event=locked_event, seeker=seeker, status=Enrollment.Status.ENROLLED
        ).exists():
            raise AlreadyEnrolled()

        if (
            locked_event.capacity is not None
            and locked_event.seats_taken >= locked_event.capacity
        ):
            raise EventFull()

        enrollment = Enrollment.objects.create(
            event=locked_event, seeker=seeker, status=Enrollment.Status.ENROLLED
        )
        Event.objects.filter(pk=locked_event.pk).update(
            seats_taken=F("seats_taken") + 1
        )

    return enrollment


def cancel_enrollment(event: Event, seeker: User) -> Enrollment:
    with transaction.atomic():
        locked_event = Event.objects.select_for_update().get(pk=event.pk)

        enrollment = Enrollment.objects.filter(
            event=locked_event, seeker=seeker, status=Enrollment.Status.ENROLLED
        ).first()
        if enrollment is None:
            raise NoActiveEnrollment()

        enrollment.status = Enrollment.Status.CANCELED
        enrollment.canceled_at = timezone.now()
        enrollment.save(update_fields=["status", "canceled_at"])

        Event.objects.filter(pk=locked_event.pk).update(
            seats_taken=F("seats_taken") - 1
        )

    return enrollment
