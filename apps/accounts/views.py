from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import SignupSerializer


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
