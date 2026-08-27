# Runs the Django app itself in production (see docker-compose.prod.yml
# and DEPLOY.md). Local dev doesn't use this image at all — dev runs
# `manage.py runserver` directly against the db/redis containers in the
# plain docker-compose.yml, which this file has no effect on.

FROM python:3.12-slim

# libpq5 is the Postgres client *library* psycopg2-binary's compiled
# wheel links against at runtime. No compiler/libpq-dev needed: the
# "-binary" package ships its own compiled extension.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
