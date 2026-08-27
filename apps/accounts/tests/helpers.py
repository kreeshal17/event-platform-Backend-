import re

from django.core import mail


def extract_otp_code(email_body: str) -> str:
    match = re.search(r"\b(\d{6})\b", email_body)
    assert match, f"no 6-digit code found in email body: {email_body!r}"
    return match.group(1)


def latest_otp_code() -> str:
    """The plaintext code from the most recently sent email."""
    return extract_otp_code(mail.outbox[-1].body)


def wrong_code(real_code: str) -> str:
    """Any 6-digit code guaranteed to differ from `real_code`."""
    return "000000" if real_code != "000000" else "111111"
