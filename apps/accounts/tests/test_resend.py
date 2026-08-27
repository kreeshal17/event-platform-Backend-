from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import EmailOTP
from apps.accounts.otp import OTP_RESEND_COOLDOWN_SECONDS, hash_otp_code

from .helpers import latest_otp_code

SIGNUP_URL = "/api/auth/signup/"
VERIFY_URL = "/api/auth/verify-email/"
RESEND_URL = "/api/auth/resend-otp/"

PASSWORD = "a-str0ng-passphrase!"


class ResendOtpTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _signup(self, email):
        response = self.client.post(
            SIGNUP_URL,
            {"email": email, "password": PASSWORD, "role": "seeker"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.content

    def _bypass_cooldown(self, email):
        """Backdates the user's latest OTP so the next resend isn't
        blocked by the 60s cooldown — simulates "enough time has passed"
        without an actual sleep in the test.
        """
        otp = EmailOTP.objects.filter(user__email=email).order_by("-created_at").first()
        otp.created_at = timezone.now() - timedelta(
            seconds=OTP_RESEND_COOLDOWN_SECONDS + 1
        )
        otp.save(update_fields=["created_at"])

    def _signup_and_resend(self, email):
        """Returns (code1, code2): the original OTP and the resent one."""
        self._signup(email)
        code1 = latest_otp_code()

        self._bypass_cooldown(email)

        resend_response = self.client.post(
            RESEND_URL, {"email": email}, format="json"
        )
        assert resend_response.status_code == status.HTTP_200_OK, resend_response.content
        code2 = latest_otp_code()
        return code1, code2

    # 6. Resend cooldown is enforced.
    def test_resend_cooldown_enforced(self):
        email = "cooldown@example.com"
        self._signup(email)  # issues OTP1 "now"

        response = self.client.post(RESEND_URL, {"email": email}, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["code"], "otp_resend_cooldown")

        # No new OTP was created.
        self.assertEqual(EmailOTP.objects.filter(user__email=email).count(), 1)

    # 7. Hourly resend cap is enforced.
    def test_hourly_resend_cap_enforced(self):
        email = "hourly.cap@example.com"
        self._signup(email)
        otp = EmailOTP.objects.get(user__email=email)
        # Backdate the signup OTP well past the cooldown, then seed 3 more
        # "prior resends" so this user has 4 OTPs total this hour, all
        # outside the 60s cooldown window.
        otp.created_at = timezone.now() - timedelta(minutes=50)
        otp.save(update_fields=["created_at"])
        for i in range(3):
            extra = EmailOTP.objects.create(
                user=otp.user,
                code_hash=hash_otp_code("000000"),
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            extra.created_at = timezone.now() - timedelta(minutes=40 - i * 5)
            extra.save(update_fields=["created_at"])

        self.assertEqual(EmailOTP.objects.filter(user__email=email).count(), 4)

        # 5th OTP this hour: still under the cap (4 < 5), allowed.
        fifth = self.client.post(RESEND_URL, {"email": email}, format="json")
        self.assertEqual(fifth.status_code, status.HTTP_200_OK)
        self.assertEqual(EmailOTP.objects.filter(user__email=email).count(), 5)

        # Bypass cooldown on the 5th so the NEXT check is unambiguously the
        # hourly cap, not the 60s cooldown.
        self._bypass_cooldown(email)

        sixth = self.client.post(RESEND_URL, {"email": email}, format="json")
        self.assertEqual(sixth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(sixth.data["code"], "otp_resend_cooldown")
        self.assertEqual(EmailOTP.objects.filter(user__email=email).count(), 5)

    # 8. Resend invalidates the previous OTP.
    def test_resend_invalidates_previous_otp(self):
        email = "invalidate@example.com"
        code1, code2 = self._signup_and_resend(email)

        self.assertNotEqual(code1, code2)
        self.assertEqual(
            EmailOTP.objects.filter(user__email=email, is_active=True).count(), 1
        )

    # 9. OTP 1 fails after OTP 2 has been issued.
    def test_otp1_fails_after_otp2_issued(self):
        email = "otp1.fails@example.com"
        code1, _code2 = self._signup_and_resend(email)

        response = self.client.post(
            VERIFY_URL, {"email": email, "otp": code1}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "otp_invalid")

    # 10. The newest OTP succeeds.
    def test_newest_otp_succeeds(self):
        email = "newest.succeeds@example.com"
        _code1, code2 = self._signup_and_resend(email)

        response = self.client.post(
            VERIFY_URL, {"email": email, "otp": code2}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_resend_with_unknown_email_returns_400(self):
        response = self.client.post(
            RESEND_URL, {"email": "nobody@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # 12. OTP never appears in any API response (resend specifically).
    def test_otp_never_appears_in_resend_response(self):
        email = "resend.no.leak@example.com"
        self._signup(email)
        self._bypass_cooldown(email)

        response = self.client.post(RESEND_URL, {"email": email}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        code = latest_otp_code()
        otp = EmailOTP.objects.filter(user__email=email).order_by("-created_at").first()
        body_text = str(response.content)
        self.assertNotIn(code, body_text)
        self.assertNotIn(otp.code_hash, body_text)

    # 15. Application code does not log the plaintext OTP (resend specifically).
    def test_resend_does_not_log_plaintext_otp(self):
        email = "resend.log.check@example.com"
        self._signup(email)
        self._bypass_cooldown(email)

        with self.assertLogs("apps.accounts", level="INFO") as captured:
            response = self.client.post(RESEND_URL, {"email": email}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        code = latest_otp_code()
        otp = EmailOTP.objects.filter(user__email=email).order_by("-created_at").first()
        self.assertEqual(hash_otp_code(code), otp.code_hash)  # confirms `code` is real

        self.assertTrue(captured.records)
        for record in captured.records:
            self.assertNotIn(code, record.getMessage())
