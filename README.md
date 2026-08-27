# Events Platform — Backend

A Django REST Framework backend for an events platform: facilitators create
events, seekers discover and enroll in them. Built in phases; see
`AGENT_SPEC.md`-derived plan below for what exists so far.

**Status: Phase 6 (enrollment lifecycle) complete.** Signup, email
verification, login, token refresh, event CRUD, event search/filtering/
ordering, and enroll/cancel/enrollment-listing all exist. Enroll's
capacity check is **deliberately naive** in this phase (see below) — the
concurrency-safe version is Phase 7. Resend and DRF throttling are not
implemented yet.

## Stack

- Django 4.2, Django REST Framework
- `django.contrib.auth.models.User` (default user model — not swapped, not
  subclassed)
- SimpleJWT for authentication
- PostgreSQL (runtime **and** tests)
- Django console email backend (development-only, see below)
- Redis (cache backend + DRF throttle state, see "Redis" below)
- `django-environ` for configuration

## Requirements

- Python 3.12
- A PostgreSQL server reachable from this machine
- A Redis server reachable from this machine
- Docker (see "Database" and "Redis" below for how this project runs both)

## Database

This project targets PostgreSQL for both runtime and the test suite —
partial unique indexes (the `LOWER(email)` constraint, the "one active
enrollment" constraint) and `select_for_update()` row locking either silently
no-op or behave differently on SQLite, so a green test suite on SQLite would
not prove the app is correct.

In this development environment there was no accessible superuser on the
machine's system PostgreSQL install (no known password, no passwordless
`sudo`), so the project runs its own PostgreSQL 16 in Docker instead of using
the system install:

```bash
docker compose up -d
```

This starts a `postgres:16` container on **host port 5433** (not 5432, to
avoid clashing with any system Postgres) with credentials taken from `.env`.
Data persists in a named Docker volume across restarts. This is just this
project's chosen way of *having* a Postgres server to point Django at —
anyone running this elsewhere can instead point `DATABASE_HOST`/`DATABASE_PORT`
in `.env` at any Postgres 16 server they already have.

The Django test runner creates/drops its own `test_<DATABASE_NAME>` database
on the same server automatically; no separate test configuration is needed.

## Redis

Redis is `CACHES["default"]` and, once auth views exist (Phase 3b), backs
DRF throttling — this is what makes throttle counters shared across Django
processes/workers instead of each process throttling independently.

**Redis is scoped to cache and throttle state only.** It never stores OTPs
or any other durable data — OTP data (`EmailOTP` rows) lives entirely in
PostgreSQL. This matters for correctness, not just tidiness: Redis data can
be evicted or flushed at any time, and if OTP business logic (the 60-second
resend cooldown, the 5-per-hour cap) depended on Redis state, an eviction
would silently hand a user extra resends. Both are instead derived from
`EmailOTP` rows in Postgres, keyed by normalized email, in Phase 3b.

Like Postgres, this project runs its own project-local Redis via Docker
(`docker compose up -d` starts both). It listens on host port **6379** and
has no auth — it's not exposed beyond the host and holds nothing durable, so
this stays intentionally minimal. Redis data lives in a named Docker volume,
though nothing currently stored in it needs to survive a restart.

**Tests never require a running Redis.** `manage.py test` sets
`DJANGO_TESTING=True` internally (see `manage.py`), which switches
`CACHES["default"]` to Django's in-process `LocMemCache` — so the default
suite is green with Redis stopped. Dedicated throttle tests, added in
Phase 3b, will reconnect to a real Redis (a separate database index, flushed
in `setUp`) specifically to test throttling, and will skip themselves with a
clear message if that Redis is unreachable rather than fail the whole suite.

**Failure mode if Redis is down at runtime:** `IGNORE_EXCEPTIONS` is
deliberately left at its default (`False`) in the `django-redis` config. If
Redis is unreachable, cache/throttle operations raise instead of silently
no-op'ing. In other words, a dead Redis surfaces as errors on throttled
endpoints rather than as unlimited, unthrottled requests — throttling fails
loudly, not open.

## Setup

```bash
# 1. Python virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Environment
cp .env.example .env
# edit .env: set a real DJANGO_SECRET_KEY and DATABASE_PASSWORD

# 3. Database + Redis
docker compose up -d

# 4. Migrate
python manage.py migrate

# 5. Run
python manage.py runserver
```

## API

### `POST /api/auth/signup/`

Public (no auth required). Body:

```json
{"email": "seeker@example.com", "password": "a-strong-password", "role": "seeker"}
```

`role` must be `"seeker"` or `"facilitator"`. A `username` field in the
request body, if present, is ignored — Django's `User` requires one, but
the client never supplies it; it's generated server-side (a UUID) and never
exposed back to the client.

On success (`201`), creates the `User` (email lowercased/normalized) and a
`Profile` with `is_email_verified=False`, and issues + emails a 6-digit OTP.
The OTP is never present in the response, in application logs, or anywhere
but its HMAC-SHA256 hash in the database. Response body:

```json
{"email": "seeker@example.com", "role": "seeker", "is_email_verified": false, "detail": "..."}
```

`400` on invalid role, weak password (Django's configured password
validators), or an email that already exists (case-insensitively) — backed
by both an application-level check and the database's partial unique index
on `LOWER(email)`, so this holds even under a signup race on the same
email.

### `POST /api/auth/verify-email/`

Public. Body: `{"email": "...", "otp": "123456"}`.

`200` with `{"detail": "Email verified."}` on the correct, unexpired code
for the latest active OTP, and marks the email verified. Coded errors
(`400` unless noted), all shaped `{"detail": "...", "code": "..."}`:

- `otp_invalid` — wrong code, **or** no active OTP for that email at all
  (including an email that was never signed up). These are deliberately
  indistinguishable so this endpoint can't be used to enumerate registered
  emails.
- `otp_expired` — the OTP's 10-minute TTL has passed.
- `otp_attempts_exceeded` — this attempt was the 5th wrong guess; the OTP
  is deactivated at that point (even the correct code stops working — a
  new one has to be issued, which is Phase 3b's resend).

### `POST /api/auth/login/`

Public. Body: `{"email": "...", "password": "..."}`.

`200` with `{"access": "...", "refresh": "..."}` (SimpleJWT tokens) once
the email is verified. `401` (DRF's stock `AuthenticationFailed`, no
`code` field yet — Phase 8's global handler normalizes this) for both
wrong password and unknown email, with an identical body either way, so
login can't be used to enumerate registered emails. `403`
`email_not_verified` for a correct password on an unverified account —
checked only *after* the password itself has already checked out, so it's
never revealed for a wrong password on an unverified account either.

### `POST /api/auth/refresh/`

Public. Body: `{"refresh": "..."}`. SimpleJWT's own stock
`TokenRefreshView` — no custom behaviour needed here.

### Events

All require authentication (a valid access token).

| Method | Path | Access |
|---|---|---|
| GET | `/api/events/` | any authenticated user |
| GET | `/api/events/{id}/` | any authenticated user |
| POST | `/api/events/` | facilitator |
| PATCH | `/api/events/{id}/` | the facilitator who owns the event |
| DELETE | `/api/events/{id}/` | the facilitator who owns the event |
| GET | `/api/facilitator/events/` | facilitator, own events only |

`POST`/`PATCH` body: `title`, `description`, `language`, `location`,
`starts_at`, `ends_at` (both ISO 8601 UTC), `capacity` (integer or `null`
for unlimited). `seats_taken` and `created_by` are always server-controlled
— present in responses, ignored if sent in a request body. `PUT` is not
supported (`405`) — only `PATCH` for partial updates, per spec.

`400` if `ends_at` is not after `starts_at`, or `capacity` is negative —
enforced both by the serializer (clean `400`) and by database
`CheckConstraint`s (`event_ends_after_starts`, `event_seats_taken_non_negative`,
`event_seats_taken_le_capacity`) as a backstop. `403` for a role/ownership
violation (wrong role on create, non-owner on update/delete).

`GET /api/facilitator/events/` returns the requesting facilitator's own
events only, each with `enrolled_count` (= `seats_taken`) and
`available_seats` (`capacity - seats_taken`, or `null` when `capacity` is
`null`) — both derived from the `seats_taken` counter on `Event`. As of
Phase 6, enroll/cancel do **not** update `seats_taken` yet (see
"Enrollment" below), so this counter and these two fields stay `0`/
`capacity` regardless of actual enrollments until Phase 7.

#### Discovery: `GET /api/events/` query parameters

| Param | Behaviour |
|---|---|
| `q` | `icontains` on `title` **or** `description` |
| `location` | exact match (not `icontains` — see note below) |
| `language` | exact match |
| `starts_after` | `starts_at` strictly after this ISO 8601 datetime |
| `starts_before` | `starts_at` strictly before this ISO 8601 datetime |

All supplied filters combine with AND. `starts_after`/`starts_before` use
strict `>`/`<` (an event starting exactly at the boundary is excluded) —
the literal reading of "after"/"before"; say the word if you want them
inclusive instead. A malformed `starts_after`/`starts_before` returns a
clean `400`, not a server error.

`location`/`language` are exact-match, not `icontains`, deliberately: they
have their own composite indexes (`(location, starts_at)`,
`(language, starts_at)`) which an exact match can actually use — unlike
`q`, which is genuine free-text search and can't use a plain B-tree index
either way (see "Known limitations" below).

Results are ordered `(starts_at < now()) ASC, starts_at ASC` — upcoming
events first (soonest first), then past events (oldest first) — exactly
matching the spec's ordering, verified directly against the generated SQL
(`ORDER BY 13 ASC, starts_at ASC` where column 13 is the `CASE WHEN
starts_at < now() THEN 1 ELSE 0 END` expression). Pagination is
`{count, next, previous, results}`, page size 20, same global DRF config
since Phase 1.

### Enrollment

| Method | Path | Access |
|---|---|---|
| POST | `/api/events/{id}/enroll/` | seeker only |
| POST | `/api/events/{id}/cancel/` | seeker only |
| GET | `/api/enrollments/?scope=upcoming\|past` | seeker only, own rows |

**Enroll** — `201` with the new `Enrollment` row (nesting a short event
summary) on success. `409` `already_enrolled` if the seeker already has
an active enrollment for this event. `409`
`{"detail": "Event is full", "code": "event_full"}` (exact spec wording)
if `capacity` is set and already met.

**⚠️ Capacity checking is deliberately naive in this phase** (Phase 6, per
spec): it counts active `Enrollment` rows and compares against `capacity`,
with no locking and no transaction around the check-then-act. This is a
genuine, exploitable race under concurrent requests — intentionally left
that way so Phase 7 (Challenge A) can demonstrate and then fix it with
`select_for_update()` and a maintained `seats_taken` counter. **Do not
rely on this endpoint enforcing capacity correctly yet.**

**Cancel** — `200`, mutates the existing active row in place
(`status="canceled"`, `canceled_at` set) — it does **not** create a new
row and does **not** delete anything. `404` `no_active_enrollment` if the
seeker has no active enrollment for this event. Also naive in this phase:
no lock, and (deliberately, to stay consistent with naive enroll never
incrementing it — see `DECISIONS.md`) does not touch `seats_taken` either.

**Re-enrolling** (enroll → cancel → enroll again) always **creates a new
row** rather than reviving the canceled one — verified by a dedicated
test (Challenge B) that checks exactly two rows exist, with different
primary keys, the older `canceled` with `canceled_at` set, and the newer
`enrolled` with `canceled_at` null. History is never deleted and a
canceled row is never flipped back to `enrolled`.

**Listing** — `GET /api/enrollments/?scope=upcoming|past` (required,
exactly one of the two) returns *every* `Enrollment` row belonging to the
requesting seeker — both active and canceled/historical — split by
whether the related event's `starts_at` is in the future or the past.
This is a deliberate reading: since Challenge B's whole point is that
canceled rows are real, permanent history, this endpoint surfaces that
history rather than silently filtering it down to active rows only. Flag
if "own rows" was meant to mean "own *active* rows" instead.

## Environment variables

See `.env.example` for the full list. Notable ones:

| Variable | Meaning | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret key | none — must be set |
| `DJANGO_DEBUG` | Debug mode | `False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,127.0.0.1` |
| `DATABASE_NAME` / `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_HOST` / `DATABASE_PORT` | Postgres connection | see `.env.example` |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | SimpleJWT access token lifetime | `15` |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | SimpleJWT refresh token lifetime | `7` |
| `REDIS_URL` | Redis connection URL for the cache backend | `redis://localhost:6379/0` |
| `REDIS_PORT` | Host port the Docker Redis binds to | `6379` |
| `AUTH_LOGIN_RATE` | DRF throttle rate, `auth_login` scope (not yet wired to a view) | `10/min` |
| `AUTH_SIGNUP_RATE` | DRF throttle rate, `auth_signup` scope (not yet wired to a view) | `5/hour` |
| `AUTH_RESEND_OTP_RATE` | DRF throttle rate, `auth_resend_otp` scope (not yet wired to a view) | `5/hour` |

`.env` is gitignored; only `.env.example` (with placeholder values) is
committed. No real secrets are committed anywhere in this repo.

## Running tests

```bash
python manage.py test
```

Requires the Postgres server from `docker compose up -d` to be running and
reachable via the `.env` settings. Does **not** require Redis — see "Redis"
above.

## Project layout

```
config/             Django project (settings, urls, wsgi/asgi)
apps/common/          shared, HTTP-layer-independent pieces: the coded
                     API exceptions used by accounts and enrollments
apps/accounts/       users, profiles, email OTP, signup/verify/login/refresh
apps/events/         Event model, CRUD, discovery, enroll/cancel views
apps/enrollments/     Enrollment model, permissions, naive enroll/cancel
                     logic, enrollment listing (seats_taken locking is
                     Phase 7)
```

`apps/` is a plain namespace directory (not a Django app itself) so app
labels stay short (`accounts`, `events`, `enrollments`) while imports are
namespaced (`apps.accounts`, ...).

## Known limitations / notes

- **Console email backend.** `EMAIL_BACKEND` is Django's console backend,
  which writes outgoing email (including, in later phases, OTP codes) to
  stdout instead of sending it. This is explicitly permitted by the
  assignment and is **development-only** — a real deployment needs a real
  email backend/provider.
- **`q` search uses `icontains`.** `icontains` on `title`/`description`
  cannot use a plain B-tree index (there's no leading prefix to seek on)
  and will degrade on a large `Event` table — unlike `location`/`language`,
  which are exact-match specifically so they *can* use their composite
  indexes. A `pg_trgm` GIN index or Postgres full-text search would be the
  production answer; deliberately not added here to keep the assignment
  compact.
- Further limitations will be added here as later phases introduce the
  behaviour they apply to.
