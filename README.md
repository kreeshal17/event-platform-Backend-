# Events Platform — Backend

A Django REST Framework backend for an events platform: facilitators create
events, seekers discover and enroll in them. Built in phases; see
`AGENT_SPEC.md`-derived plan below for what exists so far.

**Status: Phase 1 (scaffold) complete.** No API endpoints exist yet.

## Stack

- Django 4.2, Django REST Framework
- `django.contrib.auth.models.User` (default user model — not swapped, not
  subclassed)
- SimpleJWT for authentication
- PostgreSQL (runtime **and** tests)
- Django console email backend (development-only, see below)
- `django-environ` for configuration

## Requirements

- Python 3.12
- A PostgreSQL server reachable from this machine
- Docker (see "Database" below for how this project runs Postgres)

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

## Setup

```bash
# 1. Python virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Environment
cp .env.example .env
# edit .env: set a real DJANGO_SECRET_KEY and DATABASE_PASSWORD

# 3. Database
docker compose up -d

# 4. Migrate
python manage.py migrate

# 5. Run
python manage.py runserver
```

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

`.env` is gitignored; only `.env.example` (with placeholder values) is
committed. No real secrets are committed anywhere in this repo.

## Running tests

```bash
python manage.py test
```

Requires the Postgres server from `docker compose up -d` to be running and
reachable via the `.env` settings.

## Project layout

```
config/             Django project (settings, urls, wsgi/asgi)
apps/accounts/       users, profiles, email OTP (Phase 2+)
apps/events/         event model and endpoints (Phase 4+)
apps/enrollments/     enrollment lifecycle (Phase 6+)
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
- Further limitations will be added here as later phases introduce the
  behaviour they apply to (e.g. search filtering).
