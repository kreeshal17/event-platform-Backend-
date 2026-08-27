from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import (
    LoginSerializer,
    ResendOtpSerializer,
    SignupSerializer,
    VerifyEmailSerializer,
)
from .services import authenticate_and_issue_tokens, resend_otp, verify_email


class SignupView(APIView):
    """POST /api/auth/signup/

    Creates the user (with a server-generated username) and Profile, marks
    the email unverified, issues and emails an OTP. The OTP is never
    included in this response.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_signup"

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "email": user.email,
                "role": user.profile.role,
                "is_email_verified": user.profile.is_email_verified,
                "detail": "Signup successful. Check your email for a verification code.",
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    """POST /api/auth/verify-email/

    Validates the latest active OTP for `email`, enforcing expiry and the
    attempt limit, and marks the email verified on success. See
    services.verify_email() for the coded error cases. Not throttled —
    that's OTP attempt limits' job (apps.common.exceptions), a separate
    layer from DRF throttling per spec.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verify_email(
            serializer.validated_data["email"], serializer.validated_data["otp"]
        )
        return Response({"detail": "Email verified."}, status=status.HTTP_200_OK)


class LoginView(APIView):
    """POST /api/auth/login/

    Returns SimpleJWT access/refresh tokens. Unverified users get 403
    email_not_verified; unknown email and wrong password are
    indistinguishable. See services.authenticate_and_issue_tokens().
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tokens = authenticate_and_issue_tokens(
            serializer.validated_data["email"], serializer.validated_data["password"]
        )
        return Response(tokens, status=status.HTTP_200_OK)


class ResendOtpView(APIView):
    """POST /api/auth/resend-otp/

    Issues and emails a fresh OTP, enforcing the 60-second cooldown and
    5-per-hour cap, and invalidating every previously issued OTP. See
    services.resend_otp() for the cooldown/cap logic (OTP business logic,
    not DRF throttling) — throttle_scope below is a separate, coarser
    abuse-protection layer on top.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_resend_otp"

    def post(self, request):
        serializer = ResendOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.get(email=serializer.validated_data["email"])
        resend_otp(user)
        return Response(
            {"detail": "A new verification code has been sent."},
            status=status.HTTP_200_OK,
        )
