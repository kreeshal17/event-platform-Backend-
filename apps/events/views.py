from rest_framework import generics, permissions, viewsets

from .filters import EventFilterSerializer, filter_events, order_upcoming_first
from .models import Event
from .permissions import IsEventOwner, IsFacilitator
from .serializers import EventSerializer, FacilitatorEventSerializer


class EventViewSet(viewsets.ModelViewSet):
    """/api/events/ and /api/events/{id}/

    list/retrieve: any authenticated user. create: facilitator only.
    update (PATCH only — no PUT, per spec)/destroy: the owning facilitator
    only. list supports q/location/language/starts_after/starts_before
    filtering and upcoming-first ordering (see filters.py); pagination
    uses the shape/page-size already configured globally.
    """

    serializer_class = EventSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = Event.objects.all()
        if self.action == "list":
            filters = EventFilterSerializer(data=self.request.query_params)
            filters.is_valid(raise_exception=True)
            queryset = filter_events(queryset, filters.validated_data)
            queryset = order_upcoming_first(queryset)
        return queryset

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
