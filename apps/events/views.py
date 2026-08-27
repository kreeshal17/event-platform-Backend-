from rest_framework import generics, permissions, viewsets

from .models import Event
from .permissions import IsEventOwner, IsFacilitator
from .serializers import EventSerializer, FacilitatorEventSerializer


class EventViewSet(viewsets.ModelViewSet):
    """/api/events/ and /api/events/{id}/

    list/retrieve: any authenticated user. create: facilitator only.
    update (PATCH only — no PUT, per spec)/destroy: the owning facilitator
    only. No filtering, custom ordering, or pagination customization yet
    — that's Phase 5 (Discovery); this ships list/retrieve bare, on top of
    the pagination already configured globally.
    """

    queryset = Event.objects.all()
    serializer_class = EventSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsFacilitator()]
        if self.action in ("partial_update", "destroy"):
            return [permissions.IsAuthenticated(), IsFacilitator(), IsEventOwner()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class FacilitatorEventListView(generics.ListAPIView):
    """GET /api/facilitator/events/ — the requesting facilitator's own
    events only, with enrolled_count and available_seats.
    """

    serializer_class = FacilitatorEventSerializer
    permission_classes = [permissions.IsAuthenticated, IsFacilitator]

    def get_queryset(self):
        return Event.objects.filter(created_by=self.request.user)
