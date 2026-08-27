import hashlib
import hmac

from django.conf import settings
from django.test import TestCase

from apps.accounts.otp import generate_otp_code, hash_otp_code


class OTPGenerationTests(TestCase):
    def test_generate_otp_code_is_six_digits(self):
        code = generate_otp_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_generate_otp_code_is_not_constant(self):
        # Not a rigorous randomness test, just a sanity check that we're
        # not accidentally returning a fixed code.
        codes = {generate_otp_code() for _ in range(30)}
        self.assertGreater(len(codes), 1)

    def test_hash_otp_code_matches_hmac_sha256_of_secret_key(self):
        code = "123456"
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            code.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(hash_otp_code(code), expected)

    def test_hash_otp_code_does_not_return_the_plaintext(self):
        code = "654321"
        hashed = hash_otp_code(code)
        self.assertNotEqual(hashed, code)

    def test_hash_otp_code_is_deterministic(self):
        code = "111222"
        self.assertEqual(hash_otp_code(code), hash_otp_code(code))

    def test_hash_otp_code_differs_for_different_codes(self):
        self.assertNotEqual(hash_otp_code("000000"), hash_otp_code("111111"))
