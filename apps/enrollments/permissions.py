from rest_framework import permissions

from apps.accounts.models import Profile


class IsSeeker(permissions.BasePermission):
    """Allows access only to users with the seeker role.

    Assumes IsAuthenticated is also in effect — an unauthenticated request
    has no `.profile` to check.
    """

    message = "Only seekers can perform this action."

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return profile is not None and profile.role == Profile.Role.SEEKER
