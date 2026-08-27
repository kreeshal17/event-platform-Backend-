"""Small orchestration functions that earn their place by being the single
call site both signup (Phase 2) and resend (Phase 3b) will use.
"""

from .emails import send_otp_email
from .models import EmailOTP
from .otp import issue_otp


def issue_and_email_otp(user) -> EmailOTP:
    """Issue a new OTP for `user` and email it. Returns the EmailOTP row.

    The plaintext code exists only for the duration of this call and is
    never returned to the caller.
    """
    otp, code = issue_otp(user)
    send_otp_email(user, code)
    return otp
