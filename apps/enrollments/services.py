"""Enrollment business logic — deliberately naive in Phase 6, per spec.

Enroll determines capacity by COUNTING active Enrollment rows and compares
against Event.capacity. No transaction.atomic() around the check-then-act,
no select_for_update(), and Event.seats_taken is never touched. This
leaves the check-then-act race genuinely observable (Challenge A, Phase 7)
— it is not an oversight, it's the intended state of this phase.

Cancel likewise only mutates the Enrollment row (status, canceled_at). It
does not touch seats_taken and does not take a lock. This pairing is
required for consistency: Phase 6 enroll never increments the counter, so
a Phase 6 cancel that decremented it would drive seats_taken negative on
the very first cancellation and trip the seats_taken >= 0 CheckConstraint
for a reason unrelated to the lifecycle being tested here.

Both are rewritten together in Phase 7 to use transaction.atomic() +
select_for_update() and to maintain seats_taken.
"""

from django.contrib.auth.models import User
from django.utils import timezone

from apps.common.exceptions import AlreadyEnrolled, EventFull, NoActiveEnrollment
from apps.events.models import Event

from .models import Enrollment


def enroll_seeker(event: Event, seeker: User) -> Enrollment:
    if Enrollment.objects.filter(
        event=event, seeker=seeker, status=Enrollment.Status.ENROLLED
    ).exists():
        raise AlreadyEnrolled()

    if event.capacity is not None:
        active_count = Enrollment.objects.filter(
            event=event, status=Enrollment.Status.ENROLLED
        ).count()
        if active_count >= event.capacity:
            raise EventFull()

    return Enrollment.objects.create(
        event=event, seeker=seeker, status=Enrollment.Status.ENROLLED
    )


def cancel_enrollment(event: Event, seeker: User) -> Enrollment:
    enrollment = Enrollment.objects.filter(
        event=event, seeker=seeker, status=Enrollment.Status.ENROLLED
    ).first()
    if enrollment is None:
        raise NoActiveEnrollment()

    enrollment.status = Enrollment.Status.CANCELED
    enrollment.canceled_at = timezone.now()
    enrollment.save(update_fields=["status", "canceled_at"])
    return enrollment
