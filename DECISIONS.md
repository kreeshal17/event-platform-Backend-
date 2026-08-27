# Design Decisions

<!-- I (the engineer) write the reasoning here. AI fills in headers and TODO placeholders only. -->

## Decision: Redis for shared throttling

### Problem / Ambiguity

The assignment requires DRF rate limiting on login, signup, and resend-OTP,
with rates configurable via environment variables. It does not require any
particular cache backend. A rate limiter's counters need to be visible to
every Django process/worker handling requests, or the limit is effectively
per-process instead of global.

### Options Considered

- Django's in-process `LocMemCache` as the throttle cache backend.
- A Redis-backed cache (`django-redis`) as the throttle cache backend.

### Choice

Redis, as `CACHES["default"]`, is the cache backend DRF throttling reads and
writes its counters through. `LocMemCache` was rejected because it is local
to a single process: with more than one Django worker, each worker would
throttle independently, so a client could get several times the intended
rate just by landing on different workers.

PostgreSQL remains the source of truth for all application/domain data.
Redis holds only temporary cache and throttle state. OTP data is **not**
stored in Redis — the OTP resend cooldown (60s) and hourly resend cap (5/hr)
are derived from `EmailOTP` rows in PostgreSQL, keyed by normalized email,
not from Redis counters. This means a Redis eviction or restart can never
grant a user extra OTP resends: the counters that actually gate OTP
behaviour never lived in Redis to begin with.

### Trade-off

Redis adds an infrastructure dependency (another service to run, another
thing that can be down) beyond Django + PostgreSQL. In exchange, throttle
state is correctly shared across all Django workers/processes rather than
being silently per-process.

## Decision: PostgreSQL through Docker

### Problem / Ambiguity

The assignment requires PostgreSQL for both runtime and tests, since partial
unique indexes and `select_for_update()` either no-op or behave differently
on SQLite. The development machine had a PostgreSQL 16 service already
installed and running, but no usable credentials or administrative access
to it were available (no known superuser password, no passwordless `sudo`
to create one).

### Options Considered

- Obtain credentials/administrative access to the existing system
  PostgreSQL install.
- Run a project-local PostgreSQL instance in Docker instead.

### Choice

A project-local PostgreSQL 16 instance via Docker Compose. This was a
constraint of the development environment, not a preference — Docker
provided a database the project could actually create roles/databases on
without needing access that wasn't available. It runs on host port **5433**
specifically to avoid conflicting with the system PostgreSQL instance
already bound to the default port 5432.

### Trade-off

Docker becomes a local infrastructure dependency for anyone running the
project. In exchange, the database environment is fully reproducible and
isolated from whatever else may or may not be configured on the host's
system PostgreSQL install.

## Decision: Profile model for application roles

### Problem / Ambiguity

The assignment mandates using Django's default `django.contrib.auth.models.User`
as-is: no custom user model, no subclassing, no swapping `AUTH_USER_MODEL`.
The application still needs to track data `User` has no field for — role
(`seeker`/`facilitator`) and email-verification status.

### Options Considered

- A custom `User` model.
- Adding the application-specific fields directly onto `User` (not possible
  without subclassing/swapping, which is disallowed).
- A separate `Profile` model in a one-to-one relationship with `User`.

### Choice

Keep the default `User` model unmodified and store `role` and
`is_email_verified` (plus timestamps) on a separate `Profile` model with a
`OneToOneField(User)`.

### Trade-off

Every read that needs role or verification status requires an additional
relationship/join instead of a single flat row. In exchange, authentication
concerns (`User`) stay fully separate from application-specific concerns
(`Profile`), and the requirement not to touch the default user model is
satisfied without workarounds.

## Decision: New Enrollment row after re-enrollment

### Problem / Ambiguity

The re-enrollment lifecycle (enroll → cancel → enroll again) needs a
well-defined effect on the `Enrollment` table. The naive options either lose
history or allow a stale row to represent a fresh enrollment.

### Options Considered

- A permanent `unique_together(event, seeker)` constraint, which would make
  re-enrollment after a cancellation impossible without deleting the old
  row.
- Reusing the canceled row: flipping its `status` back to `enrolled` on
  re-enrollment.
- Creating a brand-new `Enrollment` row for each enrollment, leaving prior
  canceled rows untouched.

### Choice

Create a new row on every enrollment. Cancellation mutates the existing
active row in place (`status="canceled"`, `canceled_at` set) but never
deletes it, and re-enrollment always inserts a new row rather than reviving
the canceled one. This is enforced with a **partial** unique constraint —
`UniqueConstraint(fields=["event", "seeker"], condition=Q(status="enrolled"))`
— rather than an unconditional `unique_together`, so multiple canceled
historical rows are allowed while at most one active (`enrolled`) row can
exist per (event, seeker) at a time.

### Trade-off

The table accumulates more historical rows over time than the
reuse-the-row approach would. In exchange, enrollment history is
unambiguous and immutable — a canceled row is never mutated back to
`enrolled`, and each enrollment attempt (successful or superseded by a later
cancellation) has its own permanent record.

## Decision: seats_taken counter and event-row locking

### Problem / Ambiguity

Enroll and cancel both need to enforce event capacity correctly under
concurrent requests, without letting `seats_taken` exceed `capacity` or drop
below zero.

### Options Considered

- Recompute capacity on every request by counting active `Enrollment` rows
  (`COUNT(*) WHERE event=... AND status='enrolled'`).
- Rely solely on the database `CheckConstraint` (`seats_taken <= capacity`)
  with no application-level serialization.
- Maintain a denormalized `seats_taken` counter on `Event`, updated inside a
  transaction that holds a row lock on the `Event` via
  `select_for_update()`.

### Choice

The counting approach is used deliberately as the intentionally naive first
implementation, specifically to make the check-then-act race condition
observable (two concurrent requests can both count 9/10 seats taken before
either commits its insert, so both proceed). The final design instead
maintains `seats_taken` on `Event` and serializes capacity decisions:
`transaction.atomic()` + `Event.objects.select_for_update()` to lock the
event row, check capacity, create/mutate the `Enrollment` row, then update
`seats_taken` with `F("seats_taken") + 1` (enroll) or
`F("seats_taken") - 1` (cancel) — all inside the same transaction, on both
enroll and cancel. The `seats_taken <= capacity` and `seats_taken >= 0`
`CheckConstraint`s remain as a database-level backstop regardless.

### Trade-off

This introduces denormalized counter state (`seats_taken`) that must be
kept in sync with the actual count of active `Enrollment` rows — including a
data migration to backfill it correctly before the counter starts being
relied on. In exchange, capacity decisions become safe under real
concurrency (verified with a genuine multi-connection, multi-thread test)
and avoid re-counting enrollment rows on every single enroll/cancel request.

## Decision: Newest OTP invalidates previous OTPs

### Problem / Ambiguity

A user can request more than one OTP for the same signup/verification (via
resend). It needs to be unambiguous which code(s) are acceptable at
verification time once more than one has been issued.

### Options Considered

- Accept any unexpired, unconsumed OTP that was ever issued to the user.
- Invalidate all previously issued OTPs the moment a new one is issued, so
  only the newest is ever valid.

### Choice

Issuing a new OTP (via resend) invalidates every previous OTP for that user.
Only the newest active OTP can succeed verification; submitting an older
code — even one that hasn't expired and hasn't hit its attempt limit —
behaves exactly like an invalid code.

### Trade-off

A user who has an older code open in an email client (e.g. after requesting
several resends) must locate and use the newest one specifically; the older,
still-unexpired code will not work. In exchange, there is only ever one
valid verification credential outstanding at a time, which is simpler to
reason about and removes any ambiguity about which of several codes should
be accepted.

## Decision: Test cache isolation

### Problem / Ambiguity

Throttling depends on the Redis-backed cache at runtime, but the test suite
should not require a running Redis instance just to execute — a grader
without Docker running should still get a green suite. At the same time,
Redis-specific throttling behaviour genuinely needs test coverage somewhere.

### Options Considered

- Always use the Redis-backed cache in tests too, requiring Redis to be
  running for any test run.
- Always use `LocMemCache` in tests, with no dedicated Redis-backed test
  coverage at all.
- Use `LocMemCache` for the default test suite, and have a small set of
  dedicated throttle tests opt back into a real Redis connection.

### Choice

The default test suite runs against `LocMemCache` (switched in
automatically when `manage.py test` runs) and with no throttle classes
wired to any endpoint yet, so it never touches Redis and throttling plays
no role in it. Dedicated throttle tests (Phase 3b) will connect to a real
Redis explicitly, against a separate database index from the runtime one,
flush that index in `setUp`, and skip themselves with a clear message if
Redis is unreachable rather than fail the whole suite.

### Trade-off

The normal test suite does not exercise Redis at all, so dedicated
Redis-backed throttle tests are required to get real coverage of throttling
behaviour. In exchange, the ordinary test suite stays runnable in
environments without Docker/Redis available, which is the more common case
during day-to-day development and grading.

## Decision: Configurable throttle rates

### Problem / Ambiguity

DRF throttle rates for login, signup, and resend-OTP are operational policy
— values that plausibly differ between environments (development, grading,
production) — rather than fixed business logic.

### Options Considered

- Hard-code the throttle rates directly in application code/settings.
- Source the rates from environment variables, with the assignment's
  documented defaults applied when unset.

### Choice

`AUTH_LOGIN_RATE`, `AUTH_SIGNUP_RATE`, and `AUTH_RESEND_OTP_RATE` are read
from the environment (via `DEFAULT_THROTTLE_RATES` in the DRF settings),
defaulting to `10/min`, `5/hour`, and `5/hour` respectively when not set.

### Trade-off

This adds a small amount of configuration surface (three more environment
variables to document and set correctly) compared to hard-coded values. In
exchange, operational rate policy can be changed per deployment without a
code change, and the same mechanism makes it straightforward to loosen or
disable rates specifically for test environments.

## Decision: Server-generated username

### Problem / Ambiguity

Signup must accept only email, password, and role — no username — but
`django.contrib.auth.models.User` requires a non-empty, unique `username`,
and the default user model cannot be swapped or subclassed.

### Options Considered

- Derive the username deterministically from the email (e.g. the local
  part before `@`).
- Generate a random, opaque username server-side, unrelated to any
  user-supplied data.

### Choice

`uuid.uuid4().hex` is generated server-side on every signup and is never
exposed back to the client (it's not in the signup response and plays no
role in login, which is by email). Login, verification, and every other
identity check are keyed on `email`, never `username` — `username` exists
purely to satisfy `User`'s own constraint.

### Trade-off

A username derived from the email would at least be human-legible in the
Django admin; a UUID is opaque. In exchange, there's no risk of collisions
or of the generated value leaking anything about the email (case,
formatting, local-part reuse) into a field the client never asked to set.

## Decision: Signup duplicate-email race handled at two layers

### Problem / Ambiguity

Case-insensitive email uniqueness is enforced by the partial unique index
on `LOWER(email)`. Relying on the index alone means a genuine race between
two concurrent signups for the same email surfaces as an unhandled
`IntegrityError` — a `500`, not a clean validation error.

### Options Considered

- Rely solely on an application-level pre-check (`User.objects.filter(
email=...).exists()`) before creating the user.
- Rely solely on the database index and let a race surface as a `500`.
- Pre-check for the common case, and also catch `IntegrityError` from the
  index and turn it into the same `400` response for the rare race.

### Choice

Both layers: `validate_email()` rejects an already-existing email up
front (the fast path, no race involved), and `serializer.create()` wraps
user creation in `transaction.atomic()` and catches `IntegrityError`,
converting a genuine concurrent-signup race into the identical `400`
response instead of a `500`.

### Trade-off

This is a few extra lines devoted to a narrow race window (two signups for
the same email landing within the same few milliseconds). In exchange,
signup never returns an unhandled server error for a case that is fully
anticipated and already has a defined correct response.

## Decision: Coded API exceptions without the Phase 8 global handler

### Problem / Ambiguity

Verify-email and login need to return specific error codes
(`otp_expired`, `otp_invalid`, `otp_attempts_exceeded`,
`email_not_verified`) in the spec's `{"detail", "code"}` shape now, in
Phase 3a — but the assignment places the global DRF exception handler that
normalizes error shapes in Phase 8, and building it early would be running
ahead of the phase plan.

### Options Considered

- Build the Phase 8 global exception handler early, in Phase 3a, so these
  four errors already render correctly.
- Construct the `{"detail", "code"}` response body inline, by hand, in
  each view for each of these four cases.
- Define `APIException` subclasses per error, with `default_detail` set to
  the full `{"detail", "code"}` dict, relying on DRF's own default
  exception handler already returning `exc.detail` verbatim whenever it's
  a dict.

### Choice

The third option: `apps/common/exceptions.py` defines `OtpExpired`,
`OtpInvalid`, `OtpAttemptsExceeded`, and `EmailNotVerified`, each an
`APIException` whose `default_detail` is itself `{"detail": ..., "code":
...}`. Views simply `raise` them. This was checked directly against DRF's
installed source (`rest_framework/views.py`), not assumed: the default
`exception_handler` uses `exc.detail` as the entire response body whenever
`isinstance(exc.detail, (list, dict))`, so no custom handler is needed for
these four to render correctly today. Phase 8's global handler still has
real work to do — normalizing DRF's own *built-in* exception shapes
(`ValidationError`, `AuthenticationFailed`, `Throttled`, ...) into the same
shape — but has nothing to retrofit for these.

### Trade-off

This is a slightly less obvious mechanism than either building the
handler early or writing the dicts inline — a reader has to know that DRF
special-cases a dict `detail`. In exchange, the four spec-required codes
work correctly starting in Phase 3a without pulling Phase 8 forward, and
Phase 8 stays scoped to exactly what's actually left to normalize.

## Decision: Anti-enumeration on login and verify-email

### Problem / Ambiguity

Both endpoints take an `email` and something secret (a password or an
OTP). A naive implementation that returns a different error for "no such
email" versus "wrong secret" lets an attacker enumerate which emails are
registered in the system, one guess at a time.

### Options Considered

- Return distinct errors for "unknown email" vs. "wrong password"/"wrong
  code" (simpler to implement, leaks registration status).
- Return an identical response for both cases at each endpoint.

### Choice

Login raises the same `AuthenticationFailed()` — same status, same fixed
DRF message — whether the email doesn't exist or the password is wrong,
and only checks (and reveals) `email_not_verified` *after* the password
has already checked out, so a wrong password on an unverified account
doesn't leak verification status either. Verify-email folds "no such
user" and "no active OTP for this email" into the same `otp_invalid` as a
wrong code. Both are covered by tests asserting the responses are
byte-identical, not just similarly shaped.

### Trade-off

Genuine users get slightly less specific error messages (a real user who
mistypes their email gets the same message as a wrong password, not "no
such account"). In exchange, neither endpoint can be used to enumerate
which emails have signed up.

## Decision: Plain IntegerField for capacity and seats_taken

### Problem / Ambiguity

`capacity` and `seats_taken` are logically non-negative, and Django's
`PositiveIntegerField`/`PositiveSmallIntegerField` would express that
directly. Django 4.1+ also auto-generates its own implicit database CHECK
constraint for those field types.

### Options Considered

- `PositiveIntegerField` for both, relying on Django's implicit
  constraints for non-negativity, on top of the spec's three named
  `CheckConstraint`s.
- Plain `IntegerField` for both, so the three named constraints
  (`event_ends_after_starts`, `event_seats_taken_non_negative`,
  `event_seats_taken_le_capacity`) are the only mechanism enforcing
  validity.

### Choice

Plain `IntegerField`. The spec names three specific constraints as the
mechanism for enforcing Event validity; adding `PositiveIntegerField` on
top would mean two separate, unnamed-vs-named mechanisms doing
overlapping work, and an extra auto-generated constraint in every
migration that isn't one of the three the spec describes.

### Trade-off

The model class alone doesn't self-document "these are always
non-negative" the way `PositiveIntegerField` would. In exchange, the
three `CheckConstraint`s are unambiguously the complete, sole source of
truth for what values are valid — matching what's documented and tested.

## Decision: enrolled_count and available_seats sourced from seats_taken

### Problem / Ambiguity

`GET /api/facilitator/events/` needs to show how full each event is, but
Phase 4 (Events) is explicitly built before Phase 6 (Enrollment) — no
`Enrollment` model exists yet at all.

### Options Considered

- Defer `enrolled_count`/`available_seats` until Phase 6, once
  `Enrollment` exists, and ship the facilitator endpoint without them in
  Phase 4.
- Compute both directly from the `seats_taken` counter that already lives
  on `Event` as of Phase 4's own model definition.

### Choice

`enrolled_count` is `Event.seats_taken` (renamed for the API), and
`available_seats` is `capacity - seats_taken` (or `null` when `capacity`
is `null`) — both computed with no reference to `Enrollment` at all. This
is consistent with why `seats_taken` is part of the Phase 4 Event model in
the first place, rather than being introduced later alongside
`Enrollment`.

### Trade-off

Until Phase 6/7 actually wire up enrollment to move `seats_taken`, every
event's `enrolled_count` is `0` regardless of anything else — there's
nothing yet that increments it. In exchange, the facilitator endpoint's
full shape (including these two fields) ships in Phase 4 as specified,
with no dependency on a model two phases away.

## Decision: Phase 4 ships bare list/retrieve; Phase 5 adds filtering and ordering

### Problem / Ambiguity

The Event Endpoints table lists `GET /api/events/` and `GET
/api/events/{id}/` as "any authenticated" with no phase attached, while
the phase plan separately names Phase 4 "facilitator CRUD" and Phase 5
"Discovery," and Phase 5's own description names `GET /api/events/` with
its filters as that phase's deliverable — leaving it unclear whether the
list/detail endpoints exist at all before Phase 5.

### Options Considered

- Phase 4 ships only the facilitator-side endpoints (create/update/delete
  own event, list own events); `GET /api/events/` and `GET
  /api/events/{id}/` don't exist until Phase 5.
- Phase 4 ships a complete `EventViewSet` (list, retrieve, create, update,
  destroy) with list left bare — default pagination, simple `starts_at`
  ordering, no filters — and Phase 5 adds `q`/`location`/`language`/
  `starts_after`/`starts_before` and the upcoming-first ordering on top.

### Choice

The second option, confirmed explicitly before implementing Phase 4
rather than assumed. Leaving `create`/`update`/`destroy` usable while
there was no way to list or fetch a single event by id would have been an
unusual, impractical partial API, and "role permissions" (a stated Phase 4
deliverable) needs read endpoints to attach an "any authenticated" rule
to in the first place.

### Trade-off

Phase 4's list endpoint is functionally thin (no search, no meaningful
ordering) and gets substantially extended in Phase 5 rather than being
complete on arrival. In exchange, the API is usable and testable
end-to-end after Phase 4 alone, and Phase 5 is a pure enhancement of an
existing endpoint rather than its first appearance.
