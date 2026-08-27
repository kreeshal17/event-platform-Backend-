"""Outgoing email for the accounts app.

Uses settings.EMAIL_BACKEND, which is the console backend in development
(writes to stdout; see README). Never logs the code itself.
"""

from django.conf import settings
from django.core.mail import send_mail

from .otp import OTP_TTL_MINUTES


def send_otp_email(user, code: str) -> None:
    subject = "Your Events Platform verification code"
    message = (
        f"Your verification code is: {code}\n\n"
        f"This code expires in {OTP_TTL_MINUTES} minutes. "
        "If you didn't request this, you can ignore this email."
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
