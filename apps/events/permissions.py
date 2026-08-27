from rest_framework import permissions

from apps.accounts.models import Profile


class IsFacilitator(permissions.BasePermission):
    """Allows access only to users with the facilitator role.

    Assumes IsAuthenticated is also in effect — an unauthenticated request
    has no `.profile` to check.
    """

    message = "Only facilitators can perform this action."

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return profile is not None and profile.role == Profile.Role.FACILITATOR


class IsEventOwner(permissions.BasePermission):
    """Object-level permission: only the event's creator may act on it."""

    message = "You do not own this event."

    def has_object_permission(self, request, view, obj):
        return obj.created_by_id == request.user.id
