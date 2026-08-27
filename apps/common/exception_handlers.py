"""The Phase 8 global DRF exception handler.

Normalizes DRF's own *built-in* exception shapes (plain ValidationError
field-error dicts, AuthenticationFailed, NotAuthenticated,
PermissionDenied, NotFound, MethodNotAllowed, Throttled, ...) into
{"detail": "...", "code": "..."} — the shape every error response is
required to have.

It does NOT need to touch anything raised from apps.common.exceptions
(OtpExpired, OtpInvalid, AlreadyEnrolled, EventFull, ...): those already
render in exactly this shape on their own, by construction (see that
module's docstring), well before this handler was ever wired up in
Phase 8. This handler detects that shape and passes it through untouched.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.views import exception_handler as drf_default_exception_handler


def _flatten_detail(data) -> str:
    """Reduces DRF's error body (a string, a list of strings, or a
    dict of field -> list-of-strings, arbitrarily nested) down to one
    human-readable string — the first message found, depth-first.
    """
    if isinstance(data, str):
        return data
    if isinstance(data, (list, tuple)):
        for item in data:
            flattened = _flatten_detail(item)
            if flattened:
                return flattened
        return "Invalid request."
    if isinstance(data, dict):
        for value in data.values():
            flattened = _flatten_detail(value)
            if flattened:
                return flattened
        return "Invalid request."
    return str(data)


def custom_exception_handler(exc, context):
    response = drf_default_exception_handler(exc, context)
    if response is None:
        # Not something DRF's default handler recognized (e.g. an
        # unhandled exception) — let Django's own 500 handling take over,
        # same as if this handler didn't exist.
        return None

    data = response.data
    if isinstance(data, dict) and set(data.keys()) == {"detail", "code"}:
        # Already one of apps.common.exceptions' coded shapes.
        return response

    # DRF's own default_exception_handler transforms these two Django
    # exceptions into DRF equivalents internally (to build `response`
    # above), but that reassignment is local to its own function scope —
    # replicate it here too, so `exc.default_code` below refers to the
    # right class instead of Django's plain Http404/PermissionDenied,
    # neither of which has a `default_code` at all.
    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound(*exc.args)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied(*exc.args)

    if isinstance(exc, DRFValidationError):
        # DRF's own default_code for this is "invalid", which reads oddly
        # as a top-level API error code; "validation_error" is clearer
        # and still snake_case.
        code = "validation_error"
    else:
        code = getattr(exc, "default_code", None) or "error"

    response.data = {"detail": _flatten_detail(data), "code": code}
    return response
