import uuid

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import Profile
from .otp import OTP_LENGTH
from .services import issue_and_email_otp


class SignupSerializer(serializers.Serializer):
    """POST /api/auth/signup/ — email, password, role.

    Deliberately does NOT accept a `username` field: Django's User requires
    one, but the client never supplies it, per spec. Any `username` in the
    request body is simply not a field this serializer defines, so DRF
    ignores it.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=Profile.Role.choices)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return email

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data["password"]
        role = validated_data["role"]

        # The client never provides a username; Django's User still
        # requires one, so it's generated server-side and never exposed.
        username = uuid.uuid4().hex

        try:
            with transaction.atomic():
                user = User(username=username, email=email)
                user.set_password(password)
                user.save()
                Profile.objects.create(user=user, role=role)
        except IntegrityError:
            # Belt-and-suspenders against a signup race on the same email:
            # the pre-check in validate_email() can't see a concurrent
            # signup that commits between the check and this save(), but
            # the partial unique index on LOWER(email) (see migration
            # 0002) still catches it. Surface that as a normal validation
            # error instead of a 500.
            raise serializers.ValidationError(
                {"email": "A user with this email already exists."}
            )

        issue_and_email_otp(user)

        return user


class VerifyEmailSerializer(serializers.Serializer):
    """POST /api/auth/verify-email/ — email, otp.

    Only validates *format* here (well-formed email, 6-digit code). Whether
    the code is actually correct, expired, or attempts-exhausted is
    business logic handled by services.verify_email(), which raises the
    coded exceptions in apps.common.exceptions.
    """

    email = serializers.EmailField()
    otp = serializers.CharField()

    def validate_email(self, value):
        return value.strip().lower()

    def validate_otp(self, value):
        value = value.strip()
        if not (value.isdigit() and len(value) == OTP_LENGTH):
            raise serializers.ValidationError(
                f"Must be a {OTP_LENGTH}-digit code."
            )
        return value


class LoginSerializer(serializers.Serializer):
    """POST /api/auth/login/ — email, password."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.strip().lower()
