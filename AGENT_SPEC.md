# AGENT_SPEC.md — Events Platform (Django REST Backend)

You are helping me build a Django REST Framework backend assignment.

I am the engineer of record and must be able to understand and defend every
line of code and every design decision in the final repository.

Follow the instructions below STRICTLY.

---

# GLOBAL WORKING RULES

### 1. Work in phases
Complete exactly ONE phase at a time. After finishing the current phase:
run the relevant tests, show me what changed, explain the important
implementation details, tell me what to inspect, commit the work, then STOP.

Do not automatically start the next phase. Wait for my explicit instruction.

### 2. Inspect before modifying
Before implementing any phase, inspect the repository, existing files,
existing tests, `git status`, and `git log`. Understand what previous phases
already implemented. Never overwrite or recreate existing work blindly.

### 3. Do not run ahead
Do not implement future phases early. If the current phase needs something
from a later phase, implement only the minimum foundation required and tell
me why.

### 4. Do not invent requirements
Follow this spec exactly. If something is ambiguous or contradictory: STOP,
explain the ambiguity, and ask before implementing different behaviour.

### 5. Flag design problems
If you believe a decision in this spec is technically problematic, tell me
BEFORE changing it. Do not silently substitute your preferred architecture.

### 6. Keep it small
Prefer simple models, simple DRF views and serializers, clear permissions,
service functions only where they earn their place, PostgreSQL constraints,
and automated tests. Avoid unnecessary abstractions, packages, endpoints, and
infrastructure. Correctness and reasoning matter more than code volume.

### 7. Test honestly
After meaningful implementation, run the relevant tests and Django checks.
Report exactly what was run and paste the exact output. Never claim a test
passed unless you actually ran it. Never fabricate test output.

### 8. Challenges A and B are test-first
Write the test FIRST, run it, show and explain the failure, then implement the
fix, then run it again and show it passing. Do not skip the red → green
sequence. The commit history must reflect that order.

**The test always asserts the CORRECT behaviour, never the buggy behaviour.**
Red means that assertion fails. Do not write a test that expects the bug, and
do not tune assertions to match whatever the broken implementation happened to
produce.

### 9. Documentation honesty
- `README.md` — you may write setup, run instructions, architecture summary,
  API usage, and factual project information in full.
- `DECISIONS.md` — headers and `TODO` placeholders only. I write the reasoning.
- `DEBUGGING.md` — headers and `TODO` placeholders only. Do not invent
  debugging stories.
- `PROMPT_LOG.md` — table headers and `TODO` placeholders only. Do not
  fabricate AI usage.

Do not invent examples of "what AI got wrong". If I tell you about a real
mistake, help me structure the entry, but never manufacture one.

### 10. Security
Never return plaintext OTP in an API response, never log it, never print it
from application code, never expose secrets, never commit `.env`, never
hard-code the database password or `SECRET_KEY`.

The Django console email backend is permitted by the assignment and will write
the OTP to stdout. State in the README that this is development-only.

### 11. Default Django user
Use `django.contrib.auth.models.User`. Do not create a custom user model, do
not subclass `User`, do not swap `AUTH_USER_MODEL`.

### 12. Database
PostgreSQL is the target for BOTH runtime and tests. Partial unique indexes
and `select_for_update()` are silently no-ops or behave differently on SQLite,
so a green suite on SQLite would prove nothing. Configure the test database to
be PostgreSQL. If Postgres is not reachable in your environment, STOP and tell
me rather than falling back to SQLite.

### 13. Commits
Commit after every meaningful completed change, using conventional commit
messages (`feat(auth): ...`, `test(enroll): ...`, `fix(enroll): ...`,
`docs: ...`). Never create one giant final commit.

### 14. End-of-phase report
At the end of every phase, report exactly:

```
PHASE COMPLETED
FILES CHANGED
IMPORTANT IMPLEMENTATION DETAILS
TESTS RUN
TEST RESULTS
GIT COMMIT (hash + message)
WHAT I SHOULD REVIEW
QUESTIONS / RISKS
```

Then STOP and wait for my next instruction.

---

# STACK

Django 4.2+, Django REST Framework, `django.contrib.auth.models.User`,
SimpleJWT, PostgreSQL, Django console email backend, `django-environ` or
`os.environ`. Use pytest-django OR the Django test runner, but be consistent
throughout.

- `.env.example` committed, `.env` gitignored
- `USE_TZ = True`
- All API datetimes ISO 8601 UTC
- Tests run against PostgreSQL

---

# USERS AND ROLES

Signup accepts email, password, role. It MUST NOT accept username.

Django's default `User` requires a username, so generate it server-side from
the email or a UUID. The client never provides it.

`User.email` is not unique by default. Add a migration using `RunSQL` that
creates a unique index on `LOWER(email)`.

**The index must be PARTIAL.** `User.email` defaults to an empty string, so a
plain unique index breaks `createsuperuser` and any user created without an
email:

```sql
CREATE UNIQUE INDEX uniq_auth_user_lower_email
ON auth_user (LOWER(email))
WHERE email <> '';
```

Include matching reverse SQL that drops the index. Normalise email to lowercase
before saving.

```
Profile:
  user               OneToOneField(User)
  role               "seeker" | "facilitator"
  is_email_verified  boolean
  created_at, updated_at
```

Those two roles are the only valid values.

---

# EMAIL OTP

```
EmailOTP:
  user, code_hash, expires_at, attempts, is_active,
  created_at, consumed_at
```

Generate a cryptographically secure 6-digit code using the `secrets` module.
Never use `random`. Store `HMAC-SHA256(code, settings.SECRET_KEY)`. Never store,
return, or log the plaintext code.

Policy:
- TTL 10 minutes
- Max 5 failed attempts, after which the OTP is deactivated and the user must
  request a new one
- Resend cooldown 60 seconds
- Max 5 resends per hour per email
- **A resend invalidates ALL previously issued OTPs.** Only the newest is valid.
  Submitting an older code behaves exactly like an invalid code.

Error codes: `otp_expired`, `otp_invalid`, `otp_attempts_exceeded`,
`otp_resend_cooldown`, `email_not_verified`.

---

# EVENT MODEL

```
Event:
  title, description, language, location,
  starts_at (UTC), ends_at (UTC),
  capacity (nullable = unlimited),
  seats_taken (int, default 0),
  created_by FK User,
  created_at, updated_at
```

CheckConstraints:
1. `ends_at > starts_at`
2. `seats_taken >= 0`
3. `seats_taken <= capacity` where capacity is not null

Indexes: `Event(starts_at)`, `Event(location, starts_at)`,
`Event(language, starts_at)`.

---

# ENROLLMENT MODEL

```
Enrollment:
  event FK, seeker FK User,
  status: "enrolled" | "canceled",
  created_at, updated_at, canceled_at (nullable)
```

Do NOT use `unique_together(event, seeker)`. Use:

```python
UniqueConstraint(
    fields=["event", "seeker"],
    condition=Q(status="enrolled"),
    name="uniq_active_enrollment",
)
```

Many canceled historical rows are allowed; at most one active row per
(event, seeker).

Indexes: `Enrollment(event, status)`, `Enrollment(seeker, status)`.

---

# AUTH ENDPOINTS

| Method | Path | Body |
|---|---|---|
| POST | `/api/auth/signup/` | email, password, role |
| POST | `/api/auth/verify-email/` | email, otp |
| POST | `/api/auth/resend-otp/` | email |
| POST | `/api/auth/login/` | email, password |
| POST | `/api/auth/refresh/` | refresh |

Signup creates the user, generates the internal username, creates the Profile,
marks the email unverified, issues an OTP, and sends the email. The OTP is
never in the response.

Verify validates the latest active OTP, enforces expiry and attempts, marks the
email verified, and consumes the OTP.

Resend enforces cooldown and the hourly cap, invalidates all previous OTPs,
creates the newest one, and sends it.

Login returns access and refresh JWTs. An unverified user receives HTTP 403
with code `email_not_verified`.

---

# EVENT ENDPOINTS

| Method | Path | Access |
|---|---|---|
| GET | `/api/events/` | any authenticated |
| GET | `/api/events/{id}/` | any authenticated |
| POST | `/api/events/` | facilitator |
| PATCH | `/api/events/{id}/` | owner only |
| DELETE | `/api/events/{id}/` | owner only |
| GET | `/api/facilitator/events/` | facilitator, own events only |

Discovery filters: `q` (title or description, `icontains`), `location`,
`language`, `starts_after`, `starts_before`.

Pagination shape `{count, next, previous, results}`, page size 20.

Ordering: `ORDER BY (starts_at < now()) ASC, starts_at ASC` — upcoming first,
then past, each chronological.

`/api/facilitator/events/` includes `enrolled_count` and `available_seats`.
For unlimited capacity, `available_seats` is null.

---

# PERMISSIONS

Seeker: browse and search events, enroll, cancel, view own enrollments.
Facilitator: create events, view/update/delete own events, view own event
enrollment counts.

Enforce role and ownership in permission classes and queryset filtering.
Do not rely on frontend checks. Do not rely on serializer validation alone.

---

# ENROLLMENT ENDPOINTS

**POST `/api/events/{id}/enroll/`** — seeker only
- no active enrollment → `201`
- already actively enrolled → `409`, code `already_enrolled`
- event full → `409`, `{"detail": "Event is full", "code": "event_full"}`

**POST `/api/events/{id}/cancel/`** — seeker only
- active enrollment → `200`, status becomes canceled, `canceled_at` set
- no active enrollment → `404`, code `no_active_enrollment`

**GET `/api/enrollments/?scope=upcoming|past`** — seeker only, own rows only.

---

# CHALLENGE B — RE-ENROLLMENT LIFECYCLE

Required behaviour:

- Enroll → `201`, creates an Enrollment row with `status=enrolled`
- Cancel → `200`, **MUTATES that same row** to `status=canceled` and sets
  `canceled_at`. It does not create a new row.
- Enroll again → `201`, **CREATES a NEW row** with `status=enrolled`. It does
  not revive the old row.

History rows are never deleted and never flipped back from canceled to
enrolled.

Re-enrollment must re-check capacity, because another seeker may have taken
the seat after the cancellation.

### Challenge B test (write it FIRST)

After the sequence enroll → cancel → enroll, assert:

- exactly **2** Enrollment rows exist for that (event, seeker)
- the older row has `status=canceled` and `canceled_at` set
- the newer row has `status=enrolled` and `canceled_at` null
- the newer row has a different pk from the older row

Also test:
- enroll while already active → `409` `already_enrolled`
- cancel with no active enrollment → `404` `no_active_enrollment`

---

# CHALLENGE A — CONCURRENCY

Scenario: capacity 10, nine active enrollments, five seekers enroll
concurrently.

Required outcome: exactly one succeeds, four receive `event_full`, the active
enrollment count never exceeds 10, and `seats_taken` ends at 10.

Final application-layer strategy, inside `transaction.atomic()`:

1. `Event.objects.select_for_update().get(pk=...)`
2. check capacity
3. insert the Enrollment
4. increment with `F("seats_taken") + 1`

All four in the same transaction.

**Cancel uses the same pattern in its FINAL form**: `transaction.atomic()` plus
`select_for_update()` on the event, then mutate the enrollment and decrement
with `F("seats_taken") - 1`. Enroll and cancel must maintain the counter
together, introduced in the same phase. See the Phase 6 note below.

Database backstop: the `seats_taken <= capacity` CheckConstraint.

Return `409` with `{"detail": "Event is full", "code": "event_full"}` when
full. Do not silently retry.

### Challenge A test

Use `TransactionTestCase`, not `TestCase`. `TestCase` wraps each test in a
single transaction on a single connection, so the threads never truly contend
and the test passes vacuously.

Use `ThreadPoolExecutor` with 5 workers. Call `connection.close()` at the start
of each worker so each thread gets its own database connection.

**Fixture:** create the event with `capacity=10` and `seats_taken=9`, AND
create nine real Enrollment rows with `status=enrolled` for nine distinct
seekers. Both are needed, because the naive implementation counts rows and the
final implementation reads the counter.

**Assertions — correct behaviour only, in this order:**

1. exactly one of the five responses is `201`
2. the other four are `409` with code `event_full`
3. active enrollment count for the event == 10
4. `event.seats_taken` == 10

The ordering matters. Assertion 1 or 3 failing is the meaningful signal, so put
the counter assertion last.

**Do NOT assert the broken numbers.** A race is nondeterministic — under real
Postgres you might see two successes or four depending on thread and connection
timing. Never assert "5 successes" or "14 rows". The test asserts the invariant,
full stop.

**Red phase:** run this test against the naive Phase 6 implementation. It will
fail. Paste the exact failure output verbatim in your report — the actual
numbers observed are the evidence, and they belong in the report and later in
DEBUGGING.md, not in the assertions. Do not modify the test to match them.

**Green phase:** implement the fix and run the SAME unmodified test. Then run
it at least five times to confirm it is not flaky.

---

# OTP TESTS

1. Verification succeeds with the correct code
2. Wrong code is rejected
3. Expired code is rejected
4. Failed attempt limit is enforced
5. OTP becomes inactive after max attempts
6. Resend cooldown is enforced
7. Hourly resend cap is enforced
8. Resend invalidates the previous OTP
9. OTP 1 fails after OTP 2 has been issued
10. The newest OTP succeeds
11. A consumed OTP cannot be reused
12. OTP never appears in any API response
13. Verified user can log in
14. Unverified user cannot log in (403, `email_not_verified`)
15. Application code does not log the plaintext OTP

**Test 15 must use `assertLogs` against the application loggers.** It must NOT
scan stdout. The console email backend writes the code to stdout by design, so
a stdout-based assertion can never pass and would be testing the wrong thing.
The requirement is that no application logger emits the plaintext code.

---

# RATE LIMITING

Use DRF throttling on login, signup, and resend OTP.

Rates must be configurable via environment variables with sensible defaults:

```
AUTH_LOGIN_RATE       default 10/min
AUTH_SIGNUP_RATE      default 5/hour
AUTH_RESEND_OTP_RATE  default 5/hour
```

**Test settings disable throttling by default.** Dedicated throttling tests
enable the rates explicitly and clear the DRF throttle cache in `setUp`.
Without this, the sixth signup in the suite fails for reasons unrelated to the
code under test, and throttle state leaks between test methods.

Three separate layers, not to be conflated:
- DRF throttling is API abuse protection
- OTP attempt limits are verification protection
- The 60-second resend cooldown is OTP business logic

Do not use DRF throttling as a substitute for OTP attempt limits.

---

# API ERROR FORMAT

Every error response:

```json
{"detail": "Human-readable message", "code": "snake_case_code"}
```

Implement a custom DRF exception handler to normalise DRF's default shapes.

Codes: `event_full`, `already_enrolled`, `no_active_enrollment`, `otp_expired`,
`otp_invalid`, `otp_attempts_exceeded`, `otp_resend_cooldown`,
`email_not_verified`.

---

# SEED DATA

`python manage.py seed_demo` creates 2 facilitators, 12 seekers (all verified),
around 10 events with mixed languages and locations spanning past and upcoming,
one `capacity=10` event with nine active enrollments and `seats_taken=9` ready
for a manual concurrency demo, and one seeker with a completed
enroll → cancel → enroll history.

Document the demo credentials in the README. No real secrets in the repo.

---

# PHASE PLAN

### Phase 1 — Scaffold
Django project, settings, PostgreSQL config for runtime and tests,
`.env.example`, `.gitignore`, empty apps, DRF, SimpleJWT configuration,
console email backend. Commit. STOP.

### Phase 2 — Identity and OTP issuance
Profile model, partial `LOWER(email)` unique migration, signup endpoint,
EmailOTP model, secure OTP generation, HMAC hashing, OTP email, tests.
Do not implement verification, login, or resend yet. Commit. STOP.

### Phase 3a — Verification and JWT
Verify-email, login, refresh, unverified-login protection, expiry handling,
attempt limits, and their tests. Commit. STOP.

### Phase 3b — Resend and throttling
Resend endpoint, 60-second cooldown, hourly cap, invalidation of all prior
OTPs, DRF throttling with env-configurable rates, test throttle isolation, and
the remaining OTP tests including the OTP-1-after-OTP-2 case and test 15.
Commit. STOP.

### Phase 4 — Events
Event model with `seats_taken` and all three CheckConstraints, migrations,
indexes, facilitator CRUD, role permissions, ownership enforcement,
`enrolled_count` and `available_seats`. Do not implement enrollment yet.
Commit. STOP.

### Phase 5 — Discovery
`GET /api/events/` with `q`, `location`, `language`, `starts_after`,
`starts_before`, pagination, upcoming-first ordering, and tests.
Commit. STOP.

### Phase 6 — Enrollment lifecycle (Challenge B), DELIBERATELY NAIVE

Implement the Enrollment model, partial unique constraint, indexes, enroll,
cancel, and enrollment listing. Challenge B is test-first.

**Enroll is deliberately naive.** Determine capacity by COUNTING active
Enrollment rows, compare, then create the row. Do NOT use `select_for_update()`,
do NOT use `transaction.atomic()` for capacity protection, and do NOT touch
`seats_taken`. This leaves the check-then-act race genuinely observable in
Phase 7.

**Cancel is also deliberately naive in this phase.** It mutates the Enrollment
row only, setting `status=canceled` and `canceled_at`. It does NOT touch
`seats_taken` and does NOT take a lock.

This pairing is required for consistency. Phase 6 enroll never increments the
counter, so a Phase 6 cancel that decremented it would drive `seats_taken`
negative on the first cancellation and trip the `seats_taken >= 0`
CheckConstraint — which would break the Challenge B lifecycle test for a reason
that has nothing to do with the lifecycle.

`seats_taken` maintenance and its locking are introduced in Phase 7, on both
enroll and cancel together, as one change.

Commit. STOP.

### Phase 7 — Concurrency (Challenge A)

Write the concurrency test first, exactly as specified in the Challenge A
section. Run it against the naive Phase 6 implementation, show the failure, and
paste the exact output.

Then implement:
- `transaction.atomic()` and `select_for_update()` on the event, on BOTH enroll
  and cancel
- `F("seats_taken") + 1` on enroll and `F("seats_taken") - 1` on cancel
- a **data migration that backfills `seats_taken`** from the actual count of
  active Enrollment rows per event, so the counter and the CheckConstraint
  agree before the counter starts being enforced. Rows created during Phase 6
  have `seats_taken = 0` alongside real active enrollments; without the
  backfill the constraint is guarding a lie.

Run the same unmodified test, show it green, run it at least five times.

Commit as two commits:
```
test(enroll): add concurrency regression test
fix(enroll): serialize capacity checks with row lock and counter
```

STOP.

### Phase 8 — Finalisation
`seed_demo` command, custom exception handler, README, documentation
skeletons, Postman collection, full suite against PostgreSQL, `manage.py check`,
and `makemigrations --check --dry-run`. Commit. STOP.

---

# README REQUIRED NOTES

- Tests require PostgreSQL; SQLite will not exercise the constraints or locking.
- The console email backend writes the OTP to stdout; development-only.
- `q` uses `icontains`, which cannot use the B-tree indexes on Event and will
  degrade on large datasets. A `pg_trgm` GIN index or full-text search would be
  the production answer. Do not add trigram indexes without asking me — the
  assignment should stay compact.
- Any other honest limitation you hit.
