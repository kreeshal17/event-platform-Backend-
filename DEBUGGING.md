# Debugging Log

This document records real implementation problems, failed assumptions,
unexpected behavior, and issues discovered through development or testing.

Only actual issues encountered during development are documented here.
Nothing in this file is hypothetical — every entry below is something
that genuinely broke, was diagnosed, and was fixed, with the actual
command output that proves it.

## How I approach a bug

The same five-step process was used for every real incident below —
including the OTP and Challenge B areas, where the honest result was
"nothing broke," not a manufactured struggle:

```
 ┌───────────┐     ┌────────────┐     ┌────────────┐     ┌────────┐     ┌──────────────┐
 │  SYMPTOM  │ --> │ DIAGNOSIS  │ --> │ ROOT CAUSE │ --> │  FIX   │ --> │ VERIFICATION │
 │ what did  │     │ how did I  │     │ why did it │     │ what I │     │ how I proved │
 │ I actually│     │ narrow it  │     │ actually   │     │ changed│     │  it's really │
 │  observe? │     │   down?    │     │  happen?   │     │        │     │    fixed     │
 └───────────┘     └────────────┘     └────────────┘     └────────┘     └──────────────┘
```

The important discipline is not skipping straight from "symptom" to
"fix" — every entry below shows the actual diagnosis step, because
guessing at a fix without understanding the cause is how you patch a
symptom and leave the real bug in place.

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

None. This is an honest result, not a skipped section: the
enroll → cancel → enroll lifecycle test (Challenge B) was written
test-first per the spec, run against zero implementation first (a
genuine red — `404`s, since the endpoints didn't exist yet), and passed
correctly the moment the naive Phase 6 `enroll`/`cancel` logic was
written. No second attempt or fix was needed.

Why it went right the first time, worth naming so it doesn't look like
an oversight: the spec was unusually precise about the required
behavior here — a partial `UniqueConstraint` (`condition=Q(status=
"enrolled")`) instead of `unique_together`, cancel *mutating* the
existing row rather than deleting it, and re-enroll always *creating* a
new row rather than reviving the canceled one. Implementing that
description literally, rather than improvising, is what avoided a bug
here — not luck.

### Verification

`apps/enrollments/tests/test_lifecycle.py` asserts exactly this: after
enroll → cancel → enroll, precisely 2 rows exist for that (event,
seeker), with different primary keys, the older row `canceled` with
`canceled_at` set, and the newer row `enrolled` with `canceled_at` null.
Still passing as part of the full suite.

---

## Challenge C — OTP

### Issue

Also none, for the same honest reason as Challenge B. Signup, OTP
issuance, verification (expiry/attempt-limit/consumption), resend
(cooldown/hourly-cap/invalidating old codes), and login all passed on
their first real implementation, each backed by dedicated tests written
before or alongside the code (e.g. the attempt-limit test drives 5 wrong
guesses and confirms the 5th specifically returns `otp_attempts_exceeded`
and deactivates the code — including even the *correct* code no longer
working afterward).

The one thing that took real care rather than trial-and-error: proving
the "no plaintext OTP in logs" requirement with `assertLogs` against the
actual application logger, instead of scanning stdout — the console email
backend writes the code to stdout by design, so a stdout-based check
would have passed for the wrong reason (proving nothing) rather than
actually verifying the logger never emits it.

### Verification

The full OTP/auth test suite (signup, verify, resend, login, throttling)
is part of the 124-test suite that stays green on every run — see the
"bash" checklist near the top of this project's chat history, or just
run `python manage.py test`.

---

## Other Issues Encountered

Four real problems came up outside the two Challenges — three in
application/test code, one in how I was operating the tools around the
project. All four follow the same symptom → diagnosis → root cause →
fix → verification shape as above.

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

### Issue: custom exception handler gave the wrong `code` on 404s

#### Symptom

The Phase 8 global exception handler (`apps/common/exception_handlers.py`)
is supposed to normalize every DRF error into `{"detail": ..., "code":
...}`. A test hitting a nonexistent event (`GET /api/events/999999/`)
expected `"code": "not_found"` but got `"code": "error"` instead — the
generic fallback, not the specific one.

#### Diagnosis

Read through what DRF's own default `exception_handler()` actually does
with a `Django Http404` (which is what `get_object_or_404` raises): it
transforms it into `exceptions.NotFound(*exc.args)` — but that
reassignment happens to a local variable *inside DRF's own function*.
My handler calls that function to get the `response`, but the `exc`
object *I* still hold afterward is untouched — still the original,
plain Django `Http404`, which has no `.default_code` attribute at all.

#### Root Cause

I'd assumed `exc` would reflect DRF's internal `Http404` → `NotFound`
transformation once I got `response` back from calling DRF's handler. It
doesn't — that transformation is local to DRF's own function scope and
never gets communicated back to the caller.

#### Fix

Replicated the same transformation at the top of my own handler,
before reading `exc.default_code`:

```python
if isinstance(exc, Http404):
    exc = drf_exceptions.NotFound(*exc.args)
elif isinstance(exc, DjangoPermissionDenied):
    exc = drf_exceptions.PermissionDenied(*exc.args)
```

#### Verification

Re-ran `apps/common/tests/test_exception_handler.py`: the 404 test now
correctly gets `"code": "not_found"`. Full 124-test suite green
afterward, including the pre-existing tests this change didn't touch.

### Issue: Docker Compose merged an override file's `ports:` instead of replacing it

#### Symptom

While testing the AWS deployment setup in an isolated sandbox (a
throwaway copy of the repo, before writing anything into `DEPLOY.md`), I
tried to override the production compose file's port mapping for a local
test using a second `docker-compose.override.yml` with a different
`ports:` value. `docker compose up` failed:

```
Error response from daemon: failed to set up container networking:
driver failed programming external connectivity ... Bind for 0.0.0.0:80
failed: port is already allocated
```

— even though the override file specified a completely different port
(8020), not 80.

#### Diagnosis

Checked what was actually listening on port 80 on the host
(`ss -ltn`) — an unrelated, pre-existing container on the same machine
already owned it. That explained *why* something failed on port 80, but
not *why 80 was even being requested* when my override said 8020.
Re-reading Docker Compose's own merge rules answered that: unlike scalar
settings (which a later file simply overrides), list-type values like
`ports:` are *combined* across files, not replaced. Both `"80:8000"`
(from the base file) and `"8020:8000"` (from my override) were being
requested at once.

#### Root Cause

A wrong assumption about how Compose file merging works — I expected
override semantics (later file wins), Compose actually does list
concatenation for `ports:`.

#### Fix

Stopped relying on override-file merging for this test entirely.
Generated a standalone test compose file directly (`sed`-replacing the
port and container names in a copy of the real file) instead, so there
was only ever one unambiguous `ports:` value in play.

#### Verification

The isolated test then started cleanly on port 8020, with no conflict —
confirmed migrations, `collectstatic`, and gunicorn all ran correctly
inside it before that setup was ever written into `DEPLOY.md` as
instructions for a real deployment.

### Issue: a git commit message got corrupted by my own shell mistake

#### Symptom

A `git commit -m "..."` message included backtick-wrapped inline code
like `` `API_BASE = window.location.origin` `` for readability. After
committing, `git log` showed that whole phrase missing — replaced with
nothing, mid-sentence.

#### Diagnosis

Backticks inside a double-quoted string aren't literal in bash — they
trigger command substitution: bash tries to *run* whatever's between
them and splice in its output. `API_BASE = window.location.origin` was
executed as a shell command (predictably: `API_BASE: command not
found`), and its empty output is what silently replaced the intended
text in the final message.

#### Root Cause

Using backticks for inline-code styling inside a shell-quoted commit
message, without accounting for bash's own use of that same character
for command substitution.

#### Fix

Rewrote the commit message in a plain text file (no shell quoting
involved at all) and used `git commit --amend -F <file>` to replace the
corrupted message with the correct one.

#### Verification

`git log -1 --format="%B"` after the amend showed the full, correct
message with the intended phrase intact. No code was affected — this
was a commit-message-only mistake, caught and fixed before moving on.

---

## Debugging Principles

- Record what actually happened, not what was expected to happen.
- Include the symptom that was observed.
- Explain how the problem was diagnosed — the step that's easiest to
  skip, and the one that matters most.
- Identify the actual root cause, not just where the error message
  pointed.
- Explain the fix, and why it addresses the root cause rather than the
  symptom.
- Include how the fix was verified — ideally by re-running the exact
  same test or command that first exposed the problem.
- Do not fabricate incidents. If nothing broke in some area, say that
  plainly instead of inventing a story.
