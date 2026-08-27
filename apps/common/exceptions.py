"""Shared API exceptions that already carry a `code` alongside `detail`.

Each of these exploits DRF's *default* exception_handler as-is: when
`exc.detail` is itself a dict, DRF returns it as the response body
verbatim, instead of wrapping it under a `"detail"` key. So setting
`default_detail` to `{"detail": ..., "code": ...}` here already produces
exactly `{"detail": "...", "code": "..."}` on the wire, with no custom
exception handler installed.

The Phase 8 global exception handler stays future work: it only needs to
normalize DRF's own *built-in* exception shapes (plain ValidationError
field-error dicts, AuthenticationFailed, Throttled, ...) into this same
{"detail", "code"} shape — it does not need to touch anything raised from
here, since these already render correctly on their own.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class OtpExpired(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = {
        "detail": "This code has expired. Request a new one.",
        "code": "otp_expired",
    }
    default_code = "otp_expired"


class OtpInvalid(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = {
        "detail": "Invalid verification code.",
        "code": "otp_invalid",
    }
    default_code = "otp_invalid"


class OtpAttemptsExceeded(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = {
        "detail": "Too many incorrect attempts. Request a new code.",
        "code": "otp_attempts_exceeded",
    }
    default_code = "otp_attempts_exceeded"


class EmailNotVerified(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = {
        "detail": "Please verify your email before logging in.",
        "code": "email_not_verified",
    }
    default_code = "email_not_verified"


class AlreadyEnrolled(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = {
        "detail": "You are already enrolled in this event.",
        "code": "already_enrolled",
    }
    default_code = "already_enrolled"


class EventFull(APIException):
    status_code = status.HTTP_409_CONFLICT
    # Exact wording per spec: {"detail": "Event is full", "code": "event_full"}
    default_detail = {
        "detail": "Event is full",
        "code": "event_full",
    }
    default_code = "event_full"


class NoActiveEnrollment(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = {
        "detail": "You have no active enrollment in this event.",
        "code": "no_active_enrollment",
    }
    default_code = "no_active_enrollment"
