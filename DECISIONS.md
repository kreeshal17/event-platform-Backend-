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
