import uuid

from django.contrib.auth.models import User

from apps.accounts.models import Profile

PASSWORD = "a-str0ng-passphrase!"


def create_verified_user(email: str, role: str, password: str = PASSWORD) -> User:
    """A User + verified Profile, bypassing the OTP flow.

    Events tests care about role/ownership permissions, not the identity
    flow itself — that's already covered in apps.accounts.tests.
    """
    user = User.objects.create_user(
        username=uuid.uuid4().hex, email=email, password=password
    )
    Profile.objects.create(user=user, role=role, is_email_verified=True)
    return user
