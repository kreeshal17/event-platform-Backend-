# Debugging Log

This document records real implementation problems, failed assumptions,
unexpected behavior, and issues discovered through development or testing.

Only actual issues encountered during development should be documented.
Hypothetical problems must not be added.

---

## Challenge A — Enrollment Concurrency

### Red Phase

#### Symptom

Running `apps/enrollments/tests/test_concurrency.py` (5 seekers, via
`ThreadPoolExecutor`, concurrently enrolling in an event with `capacity=10`
and 9 already-active enrollments — 1 seat left) against the naive Phase 6
`enroll_seeker()` produced **2** successful (`201`) responses instead of
the required exactly 1:

```
AssertionError: 2 != 1 : results were: [(201, {'id': 11, ...}), (409, {...'code': 'event_full'}), (409, {...}), (409, {...}), (201, {'id': 10, ...})]
```

Reproduced on two separate runs with the same result (2 successes both
times, though the spec notes this is inherently nondeterministic — a
different run could show a different number).

#### Diagnosis

Both successful requests created distinct `Enrollment` rows (ids `10` and
`11`) for two different contending seekers. Both must have executed their
capacity check (`COUNT of active Enrollment rows < capacity`, i.e. `9 <
10`) before either had committed its `INSERT` — a textbook check-then-act
race, confirmed by the fact that this only happens under `TransactionTestCase`
with real concurrent threads (an earlier attempt using `TestCase` — which
shares one uncommitted transaction across "concurrent" calls — would have
passed vacuously and proven nothing).

#### Root Cause

Phase 6's `enroll_seeker()` (deliberately, per spec) determined capacity
with `Enrollment.objects.filter(...).count()` and then a separate
`Enrollment.objects.create(...)`, with no `transaction.atomic()` around
the pair and no row lock on `Event`. Nothing prevented two threads from
both reading the same pre-insert count before either wrote its row.

#### Fix

Rewrote `enroll_seeker()`/`cancel_enrollment()` (apps/enrollments/services.py)
to open `transaction.atomic()` and immediately take
`Event.objects.select_for_update()` on the event row first. This
serializes every enroll/cancel attempt for the same event: a second
thread's `SELECT ... FOR UPDATE` blocks until the first thread's
transaction commits, at which point it reads the now-updated state and
correctly sees the event full. Capacity is now checked against
`Event.seats_taken` (maintained via `F("seats_taken") + 1` / `- 1` inside
the same transaction) instead of a live `COUNT`. A data migration
(`enrollments/migrations/0002_backfill_seats_taken.py`) backfills
`seats_taken` from the real count of active `Enrollment` rows per event
before the counter starts being relied on, so it doesn't start out lying
for any event with pre-existing enrollments.

#### Verification

Re-ran the exact same, unmodified test: passed. Ran it 5 additional times
consecutively: passed every time, no flakiness. Full project suite (110
tests) also green afterward.

---

## Challenge B — Enrollment Lifecycle

### Issue

TODO

### Symptom

TODO

### Diagnosis

TODO

### Root Cause

TODO

### Fix

TODO

### Verification

TODO

---

## Challenge C — OTP

### Issue 1

#### Symptom

TODO

#### Diagnosis

TODO

#### Root Cause

TODO

#### Fix

TODO

#### Verification

TODO

### Issue 2

#### Symptom

TODO

#### Diagnosis

TODO

#### Root Cause

TODO

#### Fix

TODO

#### Verification

TODO

---

## Other Issues Encountered

Only add real issues here as they occur.

### Issue: leaked Postgres connections from concurrency test worker threads

#### Symptom

Immediately after the first (red) run of the Challenge A concurrency
test, `manage.py test` failed while tearing down the test database:

```
psycopg2.errors.ObjectInUse: database "test_events_db" is being accessed by other users
DETAIL:  There are 5 other sessions using the database.
```

The next test invocation then failed too, non-interactively, with
`EOFError: EOF when reading a line` — Django's test runner found the
leftover `test_events_db` still existing and prompted (on stdin, which
isn't available non-interactively) to confirm destroying it.

#### Diagnosis

Checked `pg_stat_activity` for the test database after the failure: the 5
sessions had already closed on their own by then (the thread pool's
threads had since exited), but too late — the teardown step itself had
already errored. Traced it to `_concurrent_enroll()` in the new test:
each worker called `connection.close()` at the *start* (per spec, to
force a fresh connection per thread) but never closed the connection it
then opened for its own request, so all 5 connections stayed open past
the end of the test method.

#### Root Cause

A raw `ThreadPoolExecutor` worker has no `request_finished` signal to
close its DB connection automatically the way a real Django
request-response cycle would — `connection.close()` was only ever called
at the start of each worker, never at the end.

#### Fix

Added `connection.close()` in a `finally` block at the end of
`_concurrent_enroll()`, so each worker's connection is released as soon
as its query work finishes, not left open until the thread itself is
eventually cleaned up.

#### Verification

Manually dropped the orphaned `test_events_db` (`DROP DATABASE IF EXISTS
test_events_db;`), then re-ran the same test: teardown completed cleanly
with no error, confirmed again across the 5 additional flakiness-check
runs and the full 110-test suite run afterward.

---

## Debugging Principles

- Record what actually happened, not what was expected to happen.
- Include the symptom that was observed.
- Explain how the problem was diagnosed.
- Identify the actual root cause.
- Explain the fix.
- Include how the fix was verified.
- Do not fabricate incidents.
