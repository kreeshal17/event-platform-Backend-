from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, SignupSerializer, VerifyEmailSerializer
from .services import authenticate_and_issue_tokens, verify_email


class SignupView(APIView):
    """POST /api/auth/signup/

    Creates the user (with a server-generated username) and Profile, marks
    the email unverified, issues and emails an OTP. The OTP is never
    included in this response.
    """

    permission_classes = [AllowAny]

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
    services.verify_email() for the coded error cases.
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

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tokens = authenticate_and_issue_tokens(
            serializer.validated_data["email"], serializer.validated_data["password"]
        )
        return Response(tokens, status=status.HTTP_200_OK)
