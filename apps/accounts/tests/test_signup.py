import re

from django.contrib.auth.models import User
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import EmailOTP, Profile
from apps.accounts.otp import hash_otp_code

SIGNUP_URL = "/api/auth/signup/"


def _extract_otp_code(email_body: str) -> str:
    match = re.search(r"\b(\d{6})\b", email_body)
    assert match, f"no 6-digit code found in email body: {email_body!r}"
    return match.group(1)


class SignupTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _payload(self, **overrides):
        payload = {
            "email": "New.Seeker@Example.com",
            "password": "a-str0ng-passphrase!",
            "role": "seeker",
        }
        payload.update(overrides)
        return payload

    def test_signup_creates_user_profile_and_otp(self):
        response = self.client.post(SIGNUP_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email="new.seeker@example.com")
        self.assertTrue(user.check_password("a-str0ng-passphrase!"))
        self.assertTrue(user.username)  # server-generated, non-empty

        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.role, Profile.Role.SEEKER)
        self.assertFalse(profile.is_email_verified)

        otp = EmailOTP.objects.get(user=user)
        self.assertTrue(otp.is_active)
        self.assertEqual(otp.attempts, 0)
        self.assertIsNone(otp.consumed_at)

    def test_signup_accepts_facilitator_role(self):
        response = self.client.post(
            SIGNUP_URL, self._payload(role="facilitator"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = Profile.objects.get(user__email="new.seeker@example.com")
        self.assertEqual(profile.role, Profile.Role.FACILITATOR)

    def test_invalid_role_rejected(self):
        response = self.client.post(
            SIGNUP_URL, self._payload(role="admin"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email="new.seeker@example.com").exists())

    def test_missing_fields_rejected(self):
        response = self.client.post(SIGNUP_URL, {"email": "x@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_is_normalized_to_lowercase(self):
        self.client.post(
            SIGNUP_URL, self._payload(email="MiXed.Case@Example.COM"), format="json"
        )
        self.assertTrue(User.objects.filter(email="mixed.case@example.com").exists())
        self.assertFalse(User.objects.filter(email="MiXed.Case@Example.COM").exists())

    def test_signup_ignores_client_supplied_username(self):
        response = self.client.post(
            SIGNUP_URL, self._payload(username="hacker"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="new.seeker@example.com")
        self.assertNotEqual(user.username, "hacker")

    def test_duplicate_email_case_insensitive_rejected_at_app_level(self):
        first = self.client.post(SIGNUP_URL, self._payload(), format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            SIGNUP_URL,
            self._payload(email="NEW.SEEKER@example.com", role="facilitator"),
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            User.objects.filter(email="new.seeker@example.com").count(), 1
        )

    def test_duplicate_email_case_insensitive_rejected_at_db_level(self):
        # Bypasses the serializer/view entirely to prove the partial unique
        # index on LOWER(email) is real database enforcement, not just
        # application-level validation.
        User.objects.create_user(username="u1", email="dup@example.com", password="x")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="u2", email="DUP@example.com", password="x"
                )

    def test_users_without_email_do_not_conflict(self):
        # Proves the unique index is PARTIAL (WHERE email <> ''): users
        # created without an email (e.g. createsuperuser flows) must not
        # collide with each other.
        User.objects.create_user(username="no-email-1", email="", password="x")
        User.objects.create_user(username="no-email-2", email="", password="x")

    def test_password_is_hashed_not_stored_plaintext(self):
        password = "a-str0ng-passphrase!"
        self.client.post(SIGNUP_URL, self._payload(password=password), format="json")
        user = User.objects.get(email="new.seeker@example.com")
        self.assertNotEqual(user.password, password)
        self.assertTrue(user.password.startswith(("pbkdf2_", "argon2", "bcrypt")))

    def test_otp_email_is_sent_and_matches_stored_hash(self):
        self.client.post(SIGNUP_URL, self._payload(), format="json")

        self.assertEqual(len(mail.outbox), 1)
        code = _extract_otp_code(mail.outbox[0].body)

        otp = EmailOTP.objects.get(user__email="new.seeker@example.com")
        self.assertEqual(hash_otp_code(code), otp.code_hash)

    def test_otp_never_appears_in_signup_response(self):
        response = self.client.post(SIGNUP_URL, self._payload(), format="json")

        code = _extract_otp_code(mail.outbox[0].body)
        otp = EmailOTP.objects.get(user__email="new.seeker@example.com")

        body_text = str(response.content)
        self.assertNotIn(code, body_text)
        self.assertNotIn(otp.code_hash, body_text)

    def test_signup_does_not_log_plaintext_otp(self):
        # Per spec: must use assertLogs against an application logger, not
        # scan stdout (the console email backend writing the code to
        # stdout is expected and is not what this test is checking).
        with self.assertLogs("apps.accounts", level="INFO") as captured:
            response = self.client.post(
                SIGNUP_URL, self._payload(email="log.check@example.com"), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        code = _extract_otp_code(mail.outbox[0].body)
        otp = EmailOTP.objects.get(user__email="log.check@example.com")
        self.assertEqual(hash_otp_code(code), otp.code_hash)  # confirms `code` is real

        self.assertTrue(captured.records)  # the app logger did emit something
        for record in captured.records:
            self.assertNotIn(code, record.getMessage())
