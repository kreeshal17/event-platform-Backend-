from django.utils import timezone
from rest_framework import generics, permissions

from .models import Enrollment
from .permissions import IsSeeker
from .serializers import EnrollmentScopeSerializer, EnrollmentSerializer


class EnrollmentListView(generics.ListAPIView):
    """GET /api/enrollments/?scope=upcoming|past — seeker only, own rows.

    "Own rows" means every Enrollment row belonging to the requesting
    seeker, regardless of status — both currently-enrolled and
    historical/canceled — split by whether the related event's starts_at
    is upcoming or past. (Not just active enrollments: Challenge B's whole
    point is that canceled rows are real history, so this view surfaces
    that history rather than hiding it.)
    """

    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsSeeker]

    def get_queryset(self):
        params = EnrollmentScopeSerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        scope = params.validated_data["scope"]

        queryset = Enrollment.objects.filter(seeker=self.request.user).select_related(
            "event"
        )
        now = timezone.now()
        if scope == "upcoming":
            queryset = queryset.filter(event__starts_at__gte=now)
        else:
            queryset = queryset.filter(event__starts_at__lt=now)
        return queryset.order_by("event__starts_at")
