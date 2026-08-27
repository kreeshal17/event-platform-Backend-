# Deploying to a single AWS EC2 instance

This runs the whole stack — the Django app, Postgres, and Redis — as
three containers on one EC2 box via `docker-compose.prod.yml`. Same
shape as local dev (`docker-compose.yml`), just with the Django app
containerized too instead of run via `manage.py runserver`.

App Runner/ECS were considered and skipped for this project: they only
run the web container, so Postgres/Redis would need RDS + ElastiCache in
a VPC with a VPC connector — three managed services and networking to
configure instead of one box running the compose file this project
already has. That trade-off is worth revisiting if this ever needs to
scale past one instance (see "What this doesn't do" below).

## 1. Launch the EC2 instance

- Ubuntu 22.04/24.04 LTS. `t3.small` (2 vCPU, 2 GB RAM) is enough for a
  demo/small workload.
- Security group: inbound 22 (SSH, from your IP only) and 80 (HTTP, from
  anywhere) — add 443 later if you put TLS in front (see below).
- Allocate an Elastic IP and associate it, so the address survives a
  reboot.

## 2. Install Docker on the instance

SSH in, then:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in for the group change to take effect
```

(This installs Docker Compose v2 as the `docker compose` subcommand —
that's what every command below uses.)

## 3. Get the code onto the instance

```bash
git clone <your-repo-url>
cd assigment
```

## 4. Configure the environment

```bash
cp .env.prod.example .env
nano .env
```

Set for real (everything else in `.env.prod.example` is already correct
for this setup):

- `DJANGO_SECRET_KEY` — generate one:
  `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
- `DJANGO_ALLOWED_HOSTS` — your Elastic IP and/or domain name
- `DATABASE_PASSWORD` — a real password, not the placeholder

## 5. Build and start everything

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This builds the app image, starts Postgres and Redis, waits for both to
report healthy, then starts the Django app. On startup the app
container runs migrations and `collectstatic` automatically (see
`entrypoint.sh`) before gunicorn starts serving — no separate manual
migrate step needed for this single-instance setup.

## 6. Verify

```bash
curl -I http://<your-ec2-ip-or-domain>/static/demo/index.html
```

Should be `200`. Then from a browser:
`http://<your-ec2-ip-or-domain>/static/demo/index.html`.

Optionally seed demo data:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py seed_demo
```

## Redeploying after a code change

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Postgres/Redis data persists in named volumes across this — only the
`web` image gets rebuilt and its container replaced.

## What this setup does NOT do (known, deliberate gaps)

- **No HTTPS.** Traffic is plain HTTP on port 80. For real use, put
  something in front that terminates TLS: either an AWS Application Load
  Balancer with an ACM certificate (targeting this instance), or a
  reverse proxy on the box itself — [Caddy](https://caddyserver.com/) is
  the simplest option, automatic Let's Encrypt certs in about 10 lines
  of config. Once there's real HTTPS in front, revisit
  `manage.py check --deploy`'s HSTS/`SECURE_SSL_REDIRECT`/secure-cookie
  warnings (see README "Deployment") — they're intentionally unset right
  now specifically because they'd be wrong without HTTPS already in
  place.
- **Single instance — no auto-scaling or failover.** Fine for a demo;
  anything real would want the database on RDS (durable, backed up,
  independent of the app instance's own lifecycle) and the app behind an
  Auto Scaling Group — a materially bigger setup than this one.
- **Migrations run automatically on every container start.** Correct and
  simple for one instance; would need to become a separate deploy step
  if this ever runs as more than one app container at a time, so they
  don't race to migrate simultaneously.
- **The demo frontend (`/static/demo/index.html`) ships in this
  deployment too**, same as everywhere else in this project — see
  README "Known limitations" for why that's fine for a
  grading/demo-scale deployment but wouldn't belong in a real product
  deployment.
