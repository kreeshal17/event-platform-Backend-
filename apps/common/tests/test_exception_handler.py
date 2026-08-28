"""The Phase 8 global exception handler.

Exercised two ways: through real endpoints for the common cases (proving
it's actually wired up end-to-end via REST_FRAMEWORK["EXCEPTION_HANDLER"],
not just correct in isolation), and directly for cases that are awkward
to trigger over real HTTP without extra setup (Throttled).
"""

from datetime import timedelta

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.common.exception_handlers import custom_exception_handler
from apps.common.exceptions import OtpInvalid
from apps.events.models import Event
from apps.events.tests.helpers import create_verified_user

EVENTS_URL = "/api/events/"


class ExceptionHandlerIntegrationTests(TestCase):
    """Every one of these hits a real view; none of them raise
    apps.common.exceptions directly, so any "code" in the response can
    only have come from the global handler normalizing a DRF built-in.
    """

    def setUp(self):
        self.client = APIClient()

    def test_validation_error_normalized(self):
        # Missing required fields -> DRF's own ValidationError.
        response = self.client.post(
            "/api/auth/signup/", {"email": "not-enough@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data.keys()), {"detail", "code"})
        self.assertEqual(response.data["code"], "validation_error")
        self.assertIsInstance(response.data["detail"], str)

    def test_not_authenticated_normalized(self):
        response = self.client.get(EVENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data, {"detail": "Authentication credentials were not provided.", "code": "not_authenticated"}
        )

    def test_permission_denied_normalized(self):
        seeker = create_verified_user("seeker@example.com", Profile.Role.SEEKER)
        self.client.force_authenticate(seeker)
        response = self.client.post(
            EVENTS_URL,
            {
                "title": "x",
                "language": "en",
                "location": "x",
                "starts_at": "2027-01-01T00:00:00Z",
                "ends_at": "2027-01-01T01:00:00Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "permission_denied")

    def test_not_found_normalized(self):
        seeker = create_verified_user("seeker2@example.com", Profile.Role.SEEKER)
        self.client.force_authenticate(seeker)
        response = self.client.get(f"{EVENTS_URL}999999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # get_object_or_404 raises Django's own Http404 with a
        # model-specific message ("No Event matches..."), not DRF's
        # generic "Not found." — the shape/code is what matters here.
        self.assertEqual(set(response.data.keys()), {"detail", "code"})
        self.assertEqual(response.data["code"], "not_found")

    def test_method_not_allowed_normalized(self):
        facilitator = create_verified_user(
            "facilitator@example.com", Profile.Role.FACILITATOR
        )
        now = timezone.now()
        event = Event.objects.create(
            title="x",
            language="en",
            location="x",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=1),
            created_by=facilitator,
        )
        self.client.force_authenticate(facilitator)
        response = self.client.put(f"{EVENTS_URL}{event.id}/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data["code"], "method_not_allowed")

    def test_our_own_coded_exceptions_pass_through_unchanged(self):
        # otp_invalid is one of apps.common.exceptions' own coded
        # exceptions — the handler must not touch it.
        response = self.client.post(
            "/api/auth/verify-email/",
            {"email": "nobody@example.com", "otp": "000000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data, {"detail": "Invalid verification code.", "code": "otp_invalid"}
        )


class ExceptionHandlerUnitTests(TestCase):
    """Direct calls for cases awkward to trigger over real HTTP here."""

    def test_throttled_normalized(self):
        response = custom_exception_handler(Throttled(wait=12), {})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["code"], "throttled")

    def test_coded_exception_passed_directly_is_unchanged(self):
        response = custom_exception_handler(OtpInvalid(), {})
        self.assertEqual(
            response.data, {"detail": "Invalid verification code.", "code": "otp_invalid"}
        )

    def test_unhandled_exception_returns_none(self):
        # Something DRF's default handler doesn't recognize at all (not
        # an APIException/Http404/PermissionDenied) — must return None so
        # Django's normal 500 handling takes over, same as if this
        # handler didn't exist.
        self.assertIsNone(custom_exception_handler(ValueError("boom"), {}))

    def test_django_permission_denied_normalized(self):
        # Mirrors test_not_found_normalized's Http404 case, but for
        # django.core.exceptions.PermissionDenied — nothing in this app
        # currently raises the *Django* PermissionDenied (view-level
        # permission checks raise DRF's own, already covered by
        # test_permission_denied_normalized above), so this branch of
        # custom_exception_handler had no coverage at all until this
        # test. It's the exact structural sibling of the Http404 ->
        # NotFound bug documented in DEBUGGING.md: a transformation DRF's
        # own default handler does internally, in its own local scope,
        # that this handler has to replicate explicitly to see it.
        response = custom_exception_handler(DjangoPermissionDenied("nope"), {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data, {"detail": "nope", "code": "permission_denied"})
