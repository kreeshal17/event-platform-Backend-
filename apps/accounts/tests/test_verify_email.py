from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import EmailOTP, Profile
from apps.accounts.otp import OTP_MAX_ATTEMPTS

from .helpers import latest_otp_code, wrong_code

SIGNUP_URL = "/api/auth/signup/"
VERIFY_URL = "/api/auth/verify-email/"


class VerifyEmailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.email = "verify.me@example.com"
        signup = self.client.post(
            SIGNUP_URL,
            {"email": self.email, "password": "a-str0ng-passphrase!", "role": "seeker"},
            format="json",
        )
        assert signup.status_code == status.HTTP_201_CREATED
        self.code = latest_otp_code()

    def _verify(self, code):
        return self.client.post(
            VERIFY_URL, {"email": self.email, "otp": code}, format="json"
        )

    # 1. Verification succeeds with the correct code.
    def test_correct_code_verifies_email(self):
        response = self._verify(self.code)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        profile = Profile.objects.get(user__email=self.email)
        self.assertTrue(profile.is_email_verified)

        otp = EmailOTP.objects.get(user__email=self.email)
        self.assertFalse(otp.is_active)
        self.assertIsNotNone(otp.consumed_at)

    # 2. Wrong code is rejected.
    def test_wrong_code_rejected(self):
        response = self._verify(wrong_code(self.code))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "otp_invalid")

        profile = Profile.objects.get(user__email=self.email)
        self.assertFalse(profile.is_email_verified)

    def test_wrong_code_increments_attempts(self):
        self._verify(wrong_code(self.code))
        otp = EmailOTP.objects.get(user__email=self.email)
        self.assertEqual(otp.attempts, 1)

    # 3. Expired code is rejected.
    def test_expired_code_rejected(self):
        EmailOTP.objects.filter(user__email=self.email).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        response = self._verify(self.code)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "otp_expired")

    # 4 & 5. Failed attempt limit is enforced; OTP becomes inactive after
    # max attempts.
    def test_attempt_limit_enforced_and_deactivates_otp(self):
        bad = wrong_code(self.code)
        for _ in range(OTP_MAX_ATTEMPTS - 1):
            response = self._verify(bad)
            self.assertEqual(response.data["code"], "otp_invalid")

        final_response = self._verify(bad)
        self.assertEqual(final_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(final_response.data["code"], "otp_attempts_exceeded")

        otp = EmailOTP.objects.get(user__email=self.email)
        self.assertFalse(otp.is_active)
        self.assertEqual(otp.attempts, OTP_MAX_ATTEMPTS)

        # Even the CORRECT code no longer works once attempts are exhausted.
        response = self._verify(self.code)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "otp_invalid")

        profile = Profile.objects.get(user__email=self.email)
        self.assertFalse(profile.is_email_verified)

    # 11. A consumed OTP cannot be reused.
    def test_consumed_otp_cannot_be_reused(self):
        first = self._verify(self.code)
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self._verify(self.code)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second.data["code"], "otp_invalid")

    def test_unknown_email_indistinguishable_from_wrong_code(self):
        wrong_code_response = self._verify(wrong_code(self.code))
        unknown_email_response = self.client.post(
            VERIFY_URL,
            {"email": "nobody-signed-up@example.com", "otp": self.code},
            format="json",
        )
        self.assertEqual(
            unknown_email_response.status_code, wrong_code_response.status_code
        )
        self.assertEqual(unknown_email_response.data, wrong_code_response.data)

    def test_malformed_otp_format_rejected(self):
        response = self.client.post(
            VERIFY_URL, {"email": self.email, "otp": "abc"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_fields_rejected(self):
        response = self.client.post(VERIFY_URL, {"email": self.email}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
