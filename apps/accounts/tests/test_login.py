from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .helpers import latest_otp_code

SIGNUP_URL = "/api/auth/signup/"
VERIFY_URL = "/api/auth/verify-email/"
LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"

PASSWORD = "a-str0ng-passphrase!"


class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _signup(self, email, password=PASSWORD, role="seeker"):
        response = self.client.post(
            SIGNUP_URL, {"email": email, "password": password, "role": role}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.content
        return response

    def _verify(self, email):
        code = latest_otp_code()
        response = self.client.post(
            VERIFY_URL, {"email": email, "otp": code}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.content

    def _login(self, email, password):
        return self.client.post(
            LOGIN_URL, {"email": email, "password": password}, format="json"
        )

    # 13. Verified user can log in.
    def test_verified_user_can_log_in(self):
        email = "verified.user@example.com"
        self._signup(email)
        self._verify(email)

        response = self._login(email, PASSWORD)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        # The access token really is a usable, correctly-claimed JWT.
        token = AccessToken(response.data["access"])
        user = User.objects.get(email=email)
        self.assertEqual(token["user_id"], user.id)

    # 14. Unverified user cannot log in (403, email_not_verified).
    def test_unverified_user_cannot_log_in(self):
        email = "unverified.user@example.com"
        self._signup(email)

        response = self._login(email, PASSWORD)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "email_not_verified")

    def test_unverified_check_only_happens_after_password_is_correct(self):
        email = "unverified.wrong.password@example.com"
        self._signup(email)

        # Wrong password on an unverified account must NOT reveal
        # email_not_verified — it's indistinguishable from any other bad
        # credentials attempt.
        response = self._login(email, "not-the-password")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("code", response.data)

    def test_wrong_password_and_unknown_email_are_indistinguishable(self):
        email = "known.user@example.com"
        self._signup(email)
        self._verify(email)

        wrong_password_response = self._login(email, "not-the-password")
        unknown_email_response = self._login("nobody@example.com", "not-the-password")

        self.assertEqual(
            wrong_password_response.status_code, unknown_email_response.status_code
        )
        self.assertEqual(
            wrong_password_response.data, unknown_email_response.data
        )
        self.assertEqual(wrong_password_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_issues_new_access_token(self):
        email = "refresh.user@example.com"
        self._signup(email)
        self._verify(email)
        login = self._login(email, PASSWORD)

        response = self.client.post(
            REFRESH_URL, {"refresh": login.data["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
