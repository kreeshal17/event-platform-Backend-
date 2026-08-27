#!/bin/sh
# Production container entrypoint: migrate + collectstatic, then serve
# with gunicorn (never `runserver` in production).
#
# Migrations run automatically on every start, which is correct and
# simple for a single instance (see DEPLOY.md). If this ever runs as
# more than one app container at once, that needs to become a separate
# deploy step instead, so N containers don't race to migrate together.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 60
