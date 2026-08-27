"""Business logic for accounts, kept independent of the HTTP layer.

Small orchestration functions that earn their place by being the single
call site multiple views (and, in Phase 3b, resend) use.
"""

import hmac

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.exceptions import (
    EmailNotVerified,
    OtpAttemptsExceeded,
    OtpExpired,
    OtpInvalid,
)

from .emails import send_otp_email
from .models import EmailOTP
from .otp import OTP_MAX_ATTEMPTS, hash_otp_code, issue_otp


def issue_and_email_otp(user) -> EmailOTP:
    """Issue a new OTP for `user` and email it. Returns the EmailOTP row.

    The plaintext code exists only for the duration of this call and is
    never returned to the caller.
    """
    otp, code = issue_otp(user)
    send_otp_email(user, code)
    return otp


def _latest_active_otp(user):
    return (
        EmailOTP.objects.filter(user=user, is_active=True)
        .order_by("-created_at")
        .first()
    )


def verify_email(email: str, code: str) -> None:
    """Validate `code` against the latest active OTP for `email`.

    Raises OtpInvalid, OtpExpired, or OtpAttemptsExceeded on failure; marks
    the user's email verified and consumes the OTP on success.

    "Wrong code" and "no active OTP for this email" (including "no such
    user") are deliberately indistinguishable — both raise OtpInvalid — so
    this endpoint can't be used to enumerate registered emails.
    """
    user = User.objects.filter(email=email).first()
    otp = _latest_active_otp(user) if user is not None else None

    if otp is None:
        raise OtpInvalid()

    if otp.expires_at <= timezone.now():
        raise OtpExpired()

    if not hmac.compare_digest(hash_otp_code(code), otp.code_hash):
        otp.attempts += 1
        attempts_exceeded = otp.attempts >= OTP_MAX_ATTEMPTS
        if attempts_exceeded:
            otp.is_active = False
        otp.save(update_fields=["attempts", "is_active"])
        raise OtpAttemptsExceeded() if attempts_exceeded else OtpInvalid()

    with transaction.atomic():
        otp.is_active = False
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["is_active", "consumed_at"])
        user.profile.is_email_verified = True
        user.profile.save(update_fields=["is_email_verified"])


def authenticate_and_issue_tokens(email: str, password: str) -> dict:
    """Returns {"access": ..., "refresh": ...} for a verified user.

    Raises AuthenticationFailed — identically, same status and message —
    for both "no such user" and "wrong password", so login can't be used
    to enumerate registered emails. Raises EmailNotVerified only once the
    password has already checked out, per spec: unverified is the one case
    that's ever revealed, and only after authentication succeeds.
    """
    user = User.objects.filter(email=email).first()
    if user is None or not user.check_password(password):
        raise AuthenticationFailed()

    if not user.profile.is_email_verified:
        raise EmailNotVerified()

    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
