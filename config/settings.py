"""
Django settings for the Events Platform backend.

See https://docs.djangoproject.com/en/4.2/topics/settings/
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_TESTING=(bool, False),
)
# Read .env from the project root if present. In real deployments the
# environment is expected to be provided by the platform instead.
environ.Env.read_env(BASE_DIR / ".env")

# Set by manage.py when invoked as `manage.py test`. Forces the cache
# backend to LocMemCache (see CACHES below) so the suite never depends on a
# running Redis. Not meant to be set by hand in a real .env.
TESTING = env("DJANGO_TESTING")


# SECURITY WARNING: keep the secret key used in production secret!
# No default is provided on purpose: the app must fail to start rather than
# silently run with a hard-coded key.
SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env("DJANGO_DEBUG")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.common",
    "apps.accounts",
    "apps.events",
    "apps.enrollments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
#
# PostgreSQL is required for both runtime and tests: partial unique indexes
# (the LOWER(email) constraint and the "one active enrollment" constraint)
# and select_for_update() either silently no-op or behave differently on
# SQLite, so a green suite on SQLite would not prove the app is correct.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DATABASE_NAME"),
        "USER": env("DATABASE_USER"),
        "PASSWORD": env("DATABASE_PASSWORD"),
        "HOST": env("DATABASE_HOST", default="localhost"),
        "PORT": env("DATABASE_PORT", default="5432"),
        # The test runner creates/drops "test_<NAME>" on this same server.
    }
}


# Cache (Redis)
#
# Redis holds temporary cache and DRF throttle state ONLY. OTP data is never
# stored here — EmailOTP rows live in PostgreSQL (see apps.accounts, Phase 2+)
# so a Redis restart/eviction can never grant a user extra OTP attempts or
# resends.
#
# Tests use LocMemCache instead (TESTING is forced True by manage.py for
# `manage.py test`), so the default suite never requires Redis to be running.
# Dedicated throttle tests (Phase 3b) opt back into a real Redis connection
# themselves, against a separate database index, and skip if it's
# unreachable.
#
# IGNORE_EXCEPTIONS is deliberately left unset (default False): if Redis is
# unreachable at runtime, cache/throttle operations raise instead of
# silently no-op'ing, so throttling fails loudly rather than quietly letting
# every request through. See README "Redis" section.

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

# Used only by apps/accounts/tests/test_throttling.py: a separate Redis
# database index from REDIS_URL's, so dedicated throttle tests exercise a
# real Redis connection without touching (or being able to collide with)
# whatever the app itself is using at runtime.
REDIS_THROTTLE_TEST_URL = env(
    "REDIS_THROTTLE_TEST_URL", default="redis://localhost:6379/15"
)

if TESTING:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
    }


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

# All stored/returned datetimes are UTC; USE_TZ makes Django timezone-aware
# throughout and DRF serializes them as ISO 8601.
TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "static/"

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Email
# The console backend prints outgoing email (including OTP codes) to stdout.
# This is explicitly permitted by the assignment and is development-only;
# see README.md.

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@events-platform.local")


# Django REST Framework
#
# DEFAULT_THROTTLE_RATES are the env-configurable rates for login/signup/
# resend-otp throttling (ScopedRateThrottle, wired onto those three views
# in Phase 3b). Rate state is stored in the "default" cache above (Redis
# outside tests, LocMemCache in tests), which is what makes throttling
# shared across processes/workers.
#
# Test settings disable throttling by default: a rate of None makes
# ScopedRateThrottle.allow_request() return True unconditionally for that
# scope (see DRF's SimpleRateThrottle), so the ordinary test suite is
# never affected by, say, the 6th signup in a test run hitting a 5/hour
# cap for reasons unrelated to what that test is checking. Dedicated
# throttling tests re-enable the real rates themselves, explicitly, via
# @override_settings(REST_FRAMEWORK={...}) — see
# apps/accounts/tests/test_throttling.py.

if TESTING:
    _auth_throttle_rates = {
        "auth_login": None,
        "auth_signup": None,
        "auth_resend_otp": None,
    }
else:
    _auth_throttle_rates = {
        "auth_login": env("AUTH_LOGIN_RATE", default="10/min"),
        "auth_signup": env("AUTH_SIGNUP_RATE", default="5/hour"),
        "auth_resend_otp": env("AUTH_RESEND_OTP_RATE", default="5/hour"),
    }

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Normalizes DRF's own built-in exception shapes into {"detail",
    # "code"} — apps.common.exceptions' coded exceptions already render
    # that way on their own and pass through this handler untouched.
    "EXCEPTION_HANDLER": "apps.common.exception_handlers.custom_exception_handler",
    "DEFAULT_THROTTLE_RATES": _auth_throttle_rates,
}


# SimpleJWT

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7)
    ),
}
