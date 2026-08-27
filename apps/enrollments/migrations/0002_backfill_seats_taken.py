# Data migration: backfill Event.seats_taken from the actual count of
# active Enrollment rows, per event.
#
# Phase 6's naive enroll/cancel never touched seats_taken, so any rows
# created during Phase 6 (or any real activity before this point) leave
# seats_taken sitting at 0 (or whatever it was seeded at) regardless of
# real active enrollments. Phase 7's enroll/cancel start relying on
# seats_taken as the source of truth for capacity — without this backfill
# the seats_taken <= capacity CheckConstraint would be guarding a lie for
# any event with pre-existing enrollments.
from django.db import migrations


def backfill_seats_taken(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Enrollment = apps.get_model("enrollments", "Enrollment")

    for event in Event.objects.all():
        active_count = Enrollment.objects.filter(
            event=event, status="enrolled"
        ).count()
        if event.seats_taken != active_count:
            event.seats_taken = active_count
            event.save(update_fields=["seats_taken"])


def noop_reverse(apps, schema_editor):
    # Nothing to reverse: the backfilled values are the correct real
    # counts, not something to undo.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("enrollments", "0001_initial"),
        ("events", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_seats_taken, noop_reverse),
    ]
