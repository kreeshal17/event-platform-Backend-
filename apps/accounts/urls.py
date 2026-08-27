from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, ResendOtpView, SignupView, VerifyEmailView

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-otp/", ResendOtpView.as_view(), name="resend-otp"),
    path("login/", LoginView.as_view(), name="login"),
    # /refresh/ is SimpleJWT's own stock view — no custom behaviour needed.
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
