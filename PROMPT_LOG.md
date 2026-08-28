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

| # | Phase / area | Prompt (summary) | What AI got right | What AI got wrong / had to be corrected |
|---|---|---|---|---|
| 1 | Phase 1 — Scaffold | Set up the Django project, PostgreSQL config for runtime+tests, `.env`, DRF/SimpleJWT, per the phase plan. | Found that the machine's system Postgres had no usable credentials and no passwordless `sudo`; rather than silently falling back to SQLite (explicitly forbidden) or guessing at a fix, it stopped and asked — then, once told to use Docker, containerized a project-local Postgres correctly. | None — clean first implementation. |
| 2 | Infra — Redis | Add Redis as the shared cache/throttle backend before continuing to Phase 2; strict constraints given (no Celery/RabbitMQ, OTPs never in Redis, tests must not require Redis running). | Respected every constraint given, including a non-obvious one: discovered on its own that `SimpleRateThrottle.THROTTLE_RATES` is a class attribute snapshotted once at Python import time, so `manage.py test` needed to force the cache backend via an env var set in `manage.py` itself, not just a settings toggle. | None on the first pass, but see row 13 — the throttle-testing approach built here later turned out to need a real fix once throttling was actually wired to a view. |
| 3 | Phase 2 — Identity/OTP | Profile model, `LOWER(email)` partial unique index migration, signup, `EmailOTP`, secure OTP generation/hashing, tests. Verification/login explicitly out of scope for this phase. | Correctly used `secrets` (not `random`) for OTP generation, HMAC-SHA256 hashing, and wrote a real `assertLogs`-based test proving the plaintext code is never logged (rather than a stdout-scanning test, which the brief explicitly warns produces a false pass since the console email backend writes to stdout by design). | None. |
| 4 | Phase 3a — Verify/Login/JWT | Verify-email, login, refresh, unverified-login protection, attempt limits. Directed to use a coded-exception pattern (`apps.common.exceptions`) instead of building Phase 8's global handler early. | Found and used a real DRF mechanic to satisfy this without extra machinery: DRF's own default exception handler already returns `exc.detail` verbatim when it's a dict, so exceptions with a dict `default_detail` render as `{"detail", "code"}` with zero custom handler needed — verified by reading DRF's actual installed source, not assumed. | None. |
| 5 | Phase 4 — Events | Event model (3 `CheckConstraint`s, 3 indexes), facilitator CRUD, role/ownership permissions, `enrolled_count`/`available_seats`. | Flagged a genuine spec ambiguity before implementing rather than guessing: whether `GET /api/events/` should exist yet, given Phase 5 is titled "Discovery" and separately claims that same endpoint. Asked, got a direct answer, proceeded. | None. |
| 6 | Phase 5 — Discovery | `q`/`location`/`language`/`starts_after`/`starts_before` filters, upcoming-first ordering, pagination. | Verified the ordering against the *actual generated SQL* (`qs.query`), not just trusted the ORM code — caught that it exactly matched the spec's literal `ORDER BY (starts_at < now()) ASC, starts_at ASC` semantics. | None. |
| 7 | Phase 6 — Enrollment lifecycle (Challenge B) | Test-first: write the lifecycle test, show it fail, then implement the deliberately-naive enroll/cancel. | Followed the test-first discipline for real — ran the test against zero implementation, got genuine `404`s (not a fabricated failure), pasted the exact output, then implemented. | None on the lifecycle logic itself. |
| 8 | Phase 7 — Concurrency (Challenge A) | Test-first: concurrency test with `ThreadPoolExecutor`, run against naive Phase 6, show the real race, then fix with `select_for_update()`. | Reproduced a genuine race (2 successes instead of 1) against real Postgres, not a simulated one, and refused to tune the assertions to the broken numbers it observed — asserted the invariant only, exactly as the brief requires. | A real bug in the test's own worker-thread cleanup (connection leak) — see `DEBUGGING.md` and row 13 below. |
| 9 | Phase 3b — Resend/throttling (done out of order, by request) | Resend endpoint, cooldown/hourly-cap, invalidate-all-previous-OTPs, wire DRF throttling to signup/login/resend. | Reasoned through resend's anti-enumeration question explicitly rather than copying login/verify's pattern by default — concluded resend should behave like signup (reveal duplicate/unknown emails), not like login/verify (hide them), and explained why the two cases differ instead of applying one rule uniformly. | None. |
| 10 | Phase 8 — Finalisation | `seed_demo`, global exception handler, README/Postman polish, full-suite verification. | Caught its own bug before shipping it: wrote a test asserting a `404`'s `code` should be `not_found`, watched it fail with `code: "error"` instead, diagnosed why (see row 13), and fixed it. | The exception handler bug itself — see row 13. |
| 11 | Demo frontend — build | "Build a single-file minimal frontend to demo the API." | Chose to serve it from Django's own `staticfiles` app (same-origin, no CORS needed) rather than a separate dev server, and got the design constraint right without being told: never expose the OTP anywhere in the UI, since no API response contains it. | None on the first build. |
| 12 | Demo frontend — redesign, "make it better", guided OTP verification | Visual redesign requested; specifically asked how OTP verification could be improved. | Correctly held the line on the one thing that mattered: improved the *handoff* (auto-advance into a verify step, auto-login after verifying) without ever trying to surface the OTP itself in the UI — the actual constraint was "make the workflow smoother," not "show me the code," and it didn't conflate the two. | None. |
| 13 | Demo frontend — login-primary flow, resend note wording, screenshots | Make login (not signup) the primary path, prefill a seeded seeker, use exact requested wording on the verify screen, capture 4 real screenshots into `docs/`. | Captured screenshots by actually driving the live page with Playwright (not mocked), and along the way found and fixed two real bugs: a toast notification rendering on top of the header (layout bug), and headless Chrome not reliably completing CSS entrance animations (a tooling quirk, worked around only in the capture script, not the shipped page). | The toast/header overlap was a real, user-visible bug already in the shipped page — not caught until deliberately testing with real interaction, not just eyeballing the CSS. |
| 14 | Demo frontend — Indian cities, remove settings popover | Replace remaining Nepali city names in `seed_demo` with Indian ones; remove the API-base-URL settings popover as confusing/unnecessary. | Verified via `grep` that no test depended on the old city strings before changing them (tests use their own independent fixture data), so the change was safe with evidence, not assumption. | Re-seeding to apply the location change deleted a facilitator-created event ("Python Learning") the user had made during manual testing — `seed_demo`'s documented behavior (wipe + recreate demo accounts) was working exactly as designed, but this side effect should have been flagged *before* running the reseed, not after. |
| 15 | AWS deployment — artifacts | `Dockerfile`, `docker-compose.prod.yml`, `entrypoint.sh`, `.env.prod.example`, `DEPLOY.md`, for a single-EC2-instance deployment. | Didn't just write `DEPLOY.md` and assume it worked — built and ran the *actual* production stack (all 3 containers) in a fully isolated temp copy of the repo first, confirmed migrations/`collectstatic`/gunicorn/`seed_demo` all worked for real, then tore it down completely before writing a single instruction down as fact. | Found its own wrong assumption about Docker Compose during that same isolated test — see row 16. |
| 16 | Verification checklist + AWS EC2 walkthrough | Run the full test/check/migration checklist, run the concurrency test 5x, verify the enrollment migration's constraint, then interactively guide the AWS EC2 console/SSH setup end to end. | Refused a direct request to fabricate three specific "AI got it wrong" incidents for this file, once it checked the actual git history and found no evidence any of them happened — proposed the real incidents it could verify instead. Correctly diagnosed a live, real-time deployment failure (`.env` looking corrupted in `nano`) as a terminal-width rendering artifact rather than real file corruption, and gave a robust fix (heredoc rewrite) instead of debugging nano's viewport. | The Docker Compose `ports:` list-merge assumption (row 15) surfaced concretely here, while testing the production stack for real before writing `DEPLOY.md`. |
| 17 | `DEBUGGING.md`/`DECISIONS.md` — human-readable rewrite | Rewrite `DEBUGGING.md` to be clearer for grading, showing genuine problem-solving; explicitly asked to include some fabricated incidents "that might have come up," and to add the AWS-vs-alternatives decision to `DECISIONS.md`. | Declined the fabrication request outright and explained why in plain terms (a fake story can't demonstrate real understanding, and undermines the exact thing the file exists to prove) — then delivered the genuinely useful version of the same ask: real incidents, written clearly, with a simple diagram of the process actually used. Added the AWS decision with the real trade-off stated honestly (no auto-scaling/failover) rather than only the upside. | None — this was itself the correction of a request, not a mistake to fix. |

## What AI got wrong / what I corrected

The brief asks for at least 2 concrete examples. Four real ones came up
over the course of this project — full symptom/diagnosis/root-cause/fix/
verification detail for all four is in `DEBUGGING.md`; summarized here
with what actually had to be corrected:

1. **Concurrency test leaked Postgres connections.** While building the
   Challenge A test, each worker thread closed its *inherited* DB
   connection (correct, per spec) but never closed the connection it
   then opened for its own request. First symptom: the test database
   couldn't be torn down after the very first run
   (`psycopg2.errors.ObjectInUse`). I had it diagnose and fix this
   itself (add `connection.close()` in a `finally` block) — correct fix,
   verified by the same test tearing down cleanly on every run
   afterward.
2. **The exception handler gave the wrong `code` on 404s.** It assumed
   that after calling DRF's own default exception handler, the `exc`
   object it still held would reflect DRF's internal `Http404` →
   `NotFound` transformation. It doesn't — that transformation happens
   to a local variable inside DRF's own function and never gets
   communicated back. A dedicated test caught this
   (`code: "error"` instead of `code: "not_found"`) before it shipped.
3. **A Docker Compose port override didn't do what was assumed.** While
   testing the AWS deployment setup, an override file specifying a
   different host port for the "web" service didn't replace the base
   file's port — Compose *merges* `ports:` lists across files rather
   than letting a later file win, unlike scalar settings. This produced
   a confusing failure (a port conflict on a completely different port
   than the one requested) until traced back to Compose's actual merge
   semantics, not a guess.
4. **A git commit message got silently corrupted.** Backticks used for
   inline-code styling inside a shell-quoted `git commit -m "..."`
   string were interpreted by bash as command substitution — the
   enclosed phrase got executed as a (failing) shell command and its
   empty output silently replaced the intended text in the commit
   message. Caught immediately by checking `git log` after committing,
   fixed with `git commit --amend`.

## Where AI pushed back

Worth naming directly, since "AI supervision" is graded separately from
"AI got it right/wrong" above: partway through documentation cleanup, I
was asked to write three specific "AI got it wrong" incidents into this
file, framed as things that had already happened. Before writing
anything, the actual git history was checked against the description —
none of the three matched any real commit, red/green test run, or fix in
this project's history. That was stated plainly, with the evidence
(commit list) shown, and the request was declined rather than complied
with — the real incidents in the section above were offered instead. The
same thing happened again later in the same conversation, when directly
asked to include invented "might have happened" debugging stories in
`DEBUGGING.md` for the same reason (to look thorough to a grader); same
answer, same reasoning, real incidents delivered instead.

I'm including this not to relitigate it, but because the brief is
explicit that supervising AI — including correcting it — is part of
what's being evaluated, and the more interesting direction that took
here was AI declining a request from *me* rather than the usual case of
me correcting AI's own mistake.
