# AI Prompt Log

Every material prompt across this project, in order. "Material" means it
drove a real, distinct piece of engineering work — routine follow-ups
within the same task ("what next", "paste the output", small
clarifications) are folded into the row they belong to rather than
listed separately, since the brief asks for prompts, not a full
transcript.

Tool/model for every row below: **Claude Code, Claude Sonnet 5**
(terminal-based agentic coding tool) — no other AI tool was used on this
project.

## AI Supervision Summary

This is a summary of what the rest of the document supports with
evidence — not a claim made in isolation:

- **Most first-pass implementations were correct.** Phases 2, 4, 5,
  Phase 3b, Challenge B, and OTP/Challenge C all passed their tests on
  the first real implementation. That's stated plainly here rather than
  manufactured into a struggle, because the brief also asks for honesty
  about *what went right*, not just what went wrong.
- **Output was not accepted unexamined.** Two genuine requirement
  ambiguities were caught and resolved with a direct question before
  implementation continued, rather than guessed at (rows 1 and 5).
- **Real defects were found and fixed, not just claimed.** Four
  implementation-level defects and three frontend/tooling issues are
  documented below with symptom, root cause, fix, and verification —
  see "Real Implementation Defects" and "Frontend & Tooling
  Corrections".
- **Claims were checked against primary evidence, not trusted at face
  value** — DRF's actual installed source was read before relying on
  its behavior, generated SQL was inspected directly rather than
  trusting the ORM, and git history was checked before writing anything
  into these docs.
- **A documentation-honesty rule was set explicitly from the start**
  (in `AGENT_SPEC.md`, this project's own working spec): no fabricated
  "what AI got wrong" content in `DEBUGGING.md`/`DECISIONS.md`/this
  file. That rule was tested directly — twice I asked for fabricated
  incidents to make this log look more thorough, and twice it was
  declined, with git history checked and real incidents offered
  instead (see "Where AI Pushed Back").

The table below tags each row with one of four labels in its last
column, so a defect isn't lost among rows that correctly had none, and
a "no defect" row isn't confused with a row that never got scrutinized:

`[No defect]` · `[Human clarification/intervention]` ·
`[AI defect — fixed]` · `[AI/tooling limitation]`

## Prompt & Supervision Table

| # | Phase / area | Prompt (summary) | What AI got right | Corrections, limitations, or human intervention |
|---|---|---|---|---|
| 1 | Phase 1 — Scaffold | Set up Django, PostgreSQL config for runtime+tests, `.env`, DRF/SimpleJWT. | Found the system Postgres had no usable credentials and no passwordless `sudo`. Did not silently fall back to SQLite (explicitly forbidden by the spec) or guess at a fix. | `[Human clarification/intervention]` Stopped and asked how to proceed rather than guessing. I directed a Docker-based project-local Postgres; AI containerized it correctly on that instruction. |
| 2 | Infra — Redis | Add Redis as the shared cache/throttle backend, before continuing to Phase 2. Constraints: no Celery/RabbitMQ/Kafka, OTPs never in Redis, tests must not require Redis running. | Respected every stated constraint, including a non-obvious one it found on its own: `SimpleRateThrottle.THROTTLE_RATES` is a class attribute snapshotted once at Python import time. | `[AI defect — fixed]` The first test-time override approach didn't actually hold once throttling was wired to real views (Phase 3b, row 9): `@override_settings` has no effect on an attribute already snapshotted at import. Corrected to `mock.patch.dict` directly on the snapshotted dict. |
| 3 | Phase 2 — Identity/OTP | Profile model, `LOWER(email)` partial unique index migration, signup, `EmailOTP`, secure OTP generation/hashing, tests. | Used `secrets` (not `random`) for OTP generation and HMAC-SHA256 for hashing. | `[No defect]` Deliberate testing decision, not a default: proved "no plaintext OTP in logs" with `assertLogs` against the real application logger, specifically *because* a stdout-scanning test would have passed for the wrong reason (the console email backend writes to stdout by design). |
| 4 | Phase 3a — Verify/Login/JWT | Verify-email, login, refresh, unverified-login protection, attempt limits. | Satisfied the coded-exception requirement with zero extra machinery, by finding that DRF's own default handler already returns `exc.detail` verbatim when it's a dict. | `[Human clarification/intervention]` + `[No defect]` I directed the architecture upfront (coded exceptions in `apps.common.exceptions`, not Phase 8's global handler yet). AI verified the mechanism against DRF's actual installed source rather than assuming it worked. |
| 5 | Phase 4 — Events | Event model (3 `CheckConstraint`s, 3 indexes), facilitator CRUD, role/ownership permissions, `enrolled_count`/`available_seats`. | — | `[Human clarification/intervention]` Flagged a genuine spec contradiction before implementing: whether `GET /api/events/` should exist yet, given Phase 5 ("Discovery") separately claims the same endpoint. Asked; I answered directly; AI proceeded on that answer. |
| 6 | Phase 5 — Discovery | `q`/`location`/`language`/`starts_after`/`starts_before` filters, upcoming-first ordering, pagination. | — | `[No defect]` Validation step, not assumption: checked the *actual generated SQL* (`qs.query`) to confirm the ordering matched the spec's literal `ORDER BY (starts_at < now()) ASC, starts_at ASC`, instead of trusting the ORM code to do what it looked like it should do. |
| 7 | Phase 6 — Enrollment lifecycle (Challenge B) | Test-first: write the lifecycle test, show it fail, implement the deliberately-naive enroll/cancel. | Followed test-first discipline for real: ran the test against zero implementation, got genuine `404`s, pasted the real output, then implemented. | `[No defect]` Passed on the first real implementation — not by luck. The spec was precise here (partial `UniqueConstraint`, cancel mutates rather than deletes, re-enroll always creates a new row), and implementing that description literally is what avoided a bug. See `DEBUGGING.md` "Challenge B" for the full reasoning. |
| 8 | Phase 7 — Concurrency (Challenge A) | Test-first: `ThreadPoolExecutor` concurrency test, run against naive Phase 6, show the real race, fix with `select_for_update()`. | Reproduced a genuine race (2 successes instead of 1) against real Postgres, not simulated. Refused to tune assertions to the broken numbers observed — asserted the invariant only. | `[AI defect — fixed]` **Postgres connection leak in the test's own worker threads** — see "Real Implementation Defects" below. |
| 9 | Phase 3b — Resend/throttling (done out of order, by request) | Resend endpoint, cooldown/hourly-cap, invalidate-all-previous-OTPs, wire DRF throttling to signup/login/resend. | Reasoned explicitly through resend's anti-enumeration question rather than copying login/verify's pattern by default — concluded resend should behave like signup (reveal duplicate/unknown emails), and explained why the two cases differ. | `[No defect]` Correct security judgment, made and explained rather than defaulted to. This is also where row 2's throttle-testing fix became necessary — see row 2. |
| 10 | Phase 8 — Finalisation | `seed_demo`, global exception handler, README/Postman polish, full-suite verification. | Caught its own bug before shipping: wrote a test asserting a `404`'s `code` should be `not_found`, watched it fail with `code: "error"`, diagnosed why, fixed it. | `[AI defect — fixed]` **Wrong `code` on 404s in the global exception handler** — see "Real Implementation Defects" below. |
| 11 | Demo frontend — build | "Build a single-file minimal frontend to demo the API." | Served it from Django's own `staticfiles` app (same-origin, no CORS) rather than a separate dev server. Self-imposed the constraint that no API response should ever contain the OTP, and built the UI accordingly without being told. | `[No defect]` Independent design decision, not directed — worth naming because it's a security-relevant default, not just a UI choice. |
| 12 | Demo frontend — redesign, guided OTP verification | Visual redesign requested; asked specifically how OTP verification UX could be improved. | Improved the *handoff* (auto-advance to verify, auto-login after verifying) without ever surfacing the OTP itself. | `[No defect]` Held a security constraint under a vague "make it better" ask instead of reinterpreting "better UX" as "show me the code" — the two are easy to conflate and weren't. |
| 13 | Demo frontend — login-primary flow, screenshots | Make login (not signup) the primary demo path, exact requested verify-screen wording, capture 4 real screenshots into `docs/`. | Captured screenshots by actually driving the live page with Playwright, not mocking it. | `[AI defect — fixed]` A toast notification was found rendering on top of the header — a real, already-shipped layout bug, not caught until deliberately testing interaction, not just reading the CSS. `[AI/tooling limitation]` Headless Chrome was also found to not reliably complete CSS entrance animations; worked around only in the capture script, not the shipped page (the bug wasn't in the app). |
| 14 | Demo frontend — Indian cities, remove settings popover | Replace Nepali city names in `seed_demo` with Indian ones; remove the API-base-URL settings popover as confusing/unnecessary. | Verified via `grep` that no test depended on the old city strings before changing them, so the change was made on evidence, not assumption. | `[AI defect — fixed, process not code]` Re-seeding to apply the change deleted a facilitator-created event ("Python Learning") I had made during manual testing. `seed_demo` did exactly what it's documented to do (wipe + recreate demo accounts) — the gap was in judgment, not code: a destructive command's side effect should have been flagged *before* running it, not explained after. |
| 15 | AWS deployment — artifacts | `Dockerfile`, `docker-compose.prod.yml`, `entrypoint.sh`, `.env.prod.example`, `DEPLOY.md`, for a single-EC2-instance deployment. | Did not write `DEPLOY.md` from assumption: built and ran the actual production stack (all 3 containers) in a fully isolated temp copy of the repo, confirmed migrations/`collectstatic`/gunicorn/`seed_demo` all worked for real, then tore it down before writing a single instruction as fact. | `[AI/tooling limitation]` **Docker Compose `ports:` merge misassumption**, found during this same isolated test — see "Real Implementation Defects" below. |
| 16 | Verification checklist + AWS EC2 walkthrough | Full test/check/migration checklist; concurrency test x5; enrollment migration review; then interactive AWS EC2 console/SSH walkthrough. | Correctly diagnosed a live deployment scare (`.env` looking corrupted in `nano`) as a terminal-width rendering artifact, not real file corruption — gave a robust fix (heredoc rewrite) instead of debugging nano's viewport. | `[AI defect — fixed]` **Git commit message corrupted by shell backtick substitution** — see "Real Implementation Defects" below. `[No defect]` Refused a direct request to fabricate three specific "AI got it wrong" incidents once git history showed no evidence for them — see "Where AI Pushed Back". |
| 17 | `DEBUGGING.md`/`DECISIONS.md` rewrite | Rewrite `DEBUGGING.md` to be clearer for grading; explicitly asked to include fabricated incidents "that might have come up"; add the AWS-vs-alternatives decision to `DECISIONS.md`. | Delivered the genuinely useful version of the request instead of the literal one: real incidents, written clearly, with a simple diagram of the process actually used. Added the AWS decision with the real trade-off (no auto-scaling/failover) stated honestly. | `[Human clarification/intervention]` (in the other direction) Declined the fabrication request outright and explained why — see "Where AI Pushed Back". |

## Real Implementation Defects

Four genuine implementation-level bugs came up. Full symptom → diagnosis
→ root cause → fix → verification detail for all four is in
`DEBUGGING.md`; this is the condensed, interviewer-facing version:

1. **Postgres connection leak in the Challenge A concurrency test**
   (row 8). Each `ThreadPoolExecutor` worker closed its *inherited* DB
   connection at the start (correct, per spec) but never closed the one
   it opened for its own request. Symptom: `manage.py test` couldn't
   tear down the test database after the first run
   (`psycopg2.errors.ObjectInUse`), then failed non-interactively on
   the next run (`EOFError`). Fix: `connection.close()` in a `finally`
   block. Verified by clean teardown across 6 subsequent runs.
2. **Wrong `code` on 404s in the global exception handler** (row 10).
   The handler assumed `exc` would reflect DRF's internal `Http404` →
   `NotFound` transformation after calling DRF's own default handler —
   it doesn't; that transformation happens to a local variable inside
   DRF's own function and is never communicated back. A dedicated test
   caught it (`code: "error"` instead of `code: "not_found"`) before it
   shipped. Fix: replicated the same `Http404`/`PermissionDenied`
   transformation explicitly at the top of the custom handler.
3. **Docker Compose `ports:` merge misassumption** (row 15). While
   testing the AWS deployment setup in isolation, an override file
   specifying a different host port for the "web" service didn't
   replace the base file's port — Compose *merges* `ports:` lists
   across files rather than letting a later file win, unlike scalar
   settings. Produced a confusing failure (a conflict on a port that
   wasn't even the one requested) until traced to Compose's actual
   merge semantics. Fix: generated a standalone test compose file
   instead of relying on override-merge behavior.
4. **Git commit message corrupted by shell backtick substitution**
   (row 16). Backticks used for inline-code styling inside a
   shell-quoted `git commit -m "..."` string were interpreted by bash
   as command substitution — the enclosed phrase was executed as a
   (failing) shell command, and its empty output silently replaced the
   intended text. Caught by checking `git log` immediately after
   committing. Fixed with `git commit --amend -F <file>` using a plain
   text file, avoiding shell quoting entirely.

## Frontend & Tooling Corrections

Separate from the four defects above because these surfaced through
*interacting* with the running app, not through a failing test — worth
distinguishing because it's different evidence of supervision (manual
verification, not just automated):

1. **Toast/header overlap** (row 13). A toast notification rendered on
   top of the page header — a real, already-shipped layout bug, found
   only by driving the live page with Playwright and watching an actual
   interaction, not by reading the CSS. Fixed in the shipped page.
2. **Headless Chrome doesn't reliably complete CSS entrance
   animations** (row 13). A tooling limitation, not an app bug —
   affected only the screenshot-capture script, worked around there
   without touching the shipped page.
3. **Reseeding deleted a manually-created demo event** (row 14).
   Re-running `seed_demo` to pick up the Indian-city location change
   wiped a facilitator-created event ("Python Learning") made earlier
   during manual testing. `seed_demo` behaved exactly as documented
   (wipe + recreate demo accounts) — the failure was not flagging that
   consequence *before* running a destructive command, not a bug in the
   command itself.

## Where AI Pushed Back

Worth treating as its own category of evidence, since "AI supervision"
in the brief is graded separately from "AI got it right/wrong" above —
and because a refusal is a different, arguably stronger, kind of
supervision signal than a correction.

This project's own working spec (`AGENT_SPEC.md`) set an explicit rule
from the start: no fabricated content in `DEBUGGING.md`, `DECISIONS.md`,
or this file. That rule was tested directly, twice, by me:

1. Partway through documentation cleanup, I asked for three specific
   "AI got it wrong" incidents to be written into this file, framed as
   things that had already happened. Before writing anything, AI
   checked the actual `git log` history against the description — none
   of the three matched any real commit, red/green test run, or fix.
   That was stated plainly, with the evidence (commit list) shown, and
   the request was declined. The four real incidents in "Real
   Implementation Defects" above were offered instead.
2. Later in the same conversation, I asked directly for invented
   "might have happened" debugging stories in `DEBUGGING.md`, for the
   same reason — to look more thorough to a grader. Same check, same
   refusal, same reasoning, real incidents delivered instead.

The useful framing for an interviewer: this isn't a case of AI
spontaneously deciding to be honest — it's a case of a rule I set
explicitly at the start of the project being upheld even when I later,
directly, asked for it to be broken. That's the actual test of whether
a supervision rule works: not whether it's followed when no one asks it
to bend, but whether it holds when someone does.

## Evidence of Human Verification

None of the claims in this document rest on AI's word alone. Concrete,
repeatable verification behind them:

- **The concurrency invariant was checked repeatedly, not once.** The
  Challenge A test was re-run 5 additional times after the fix (plus
  again independently while preparing this log) specifically to check
  for flakiness, not just a single pass.
- **Every claim above about test results is backed by the full suite**
  — 124 tests, run against real PostgreSQL (+ Redis for
  cache/throttling), not SQLite or mocks.
- **The production deployment was tested before being documented.**
  The full Docker production stack (app + Postgres + Redis, 3
  containers) was built and run in an isolated copy of the repo —
  migrations, `collectstatic`, gunicorn, `seed_demo` all confirmed
  working for real — before a single instruction went into `DEPLOY.md`.
  It's since been deployed for real to a live AWS EC2 instance, with
  HTTPS added afterward and confirmed with `curl` (valid Let's Encrypt
  certificate, HSTS header present, `http://` → `https://` redirect
  working).
- **Screenshots came from the live frontend, not mockups.** The 4
  screenshots embedded in the README were captured with Playwright
  actually driving the running demo page.
- **Ordering logic was checked against generated SQL**, not trusted
  ORM code — `qs.query` was inspected directly to confirm the Phase 5
  discovery ordering matched the spec's literal SQL.
- **The coded-exception mechanism was checked against DRF's actual
  installed source**, not assumed from documentation or memory.
- **Every "what AI got wrong" claim in this file was checked against
  real git history before being written down** — including rejecting
  three specific incidents that a plain reading of the history did not
  support (see "Where AI Pushed Back").
