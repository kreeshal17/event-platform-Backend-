"""OTP generation and hashing.

The plaintext code is never stored, logged, or returned by any function
here except as an explicit return value the caller must handle carefully
(email it, then discard it).
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EmailOTP

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10

_DIGITS = "0123456789"


def generate_otp_code() -> str:
    """A cryptographically secure OTP_LENGTH-digit numeric code.

    Uses `secrets`, not `random`, per spec — `random` is not suitable for
    anything security-sensitive.
    """
    return "".join(secrets.choice(_DIGITS) for _ in range(OTP_LENGTH))


def hash_otp_code(code: str) -> str:
    """HMAC-SHA256(code, settings.SECRET_KEY), hex-encoded."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_otp(user) -> tuple[EmailOTP, str]:
    """Create a new active EmailOTP row for `user`.

    Returns (otp, plaintext_code). The plaintext code is not persisted
    anywhere by this function — only its hash is. The caller is responsible
    for emailing the plaintext code and must not log or store it.
    """
    code = generate_otp_code()
    otp = EmailOTP.objects.create(
        user=user,
        code_hash=hash_otp_code(code),
        expires_at=timezone.now() + timedelta(minutes=OTP_TTL_MINUTES),
    )
    # Deliberately no plaintext code in this log line.
    logger.info("OTP issued for user_id=%s otp_id=%s", user.id, otp.id)
    return otp, code
