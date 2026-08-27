from django.urls import path

from .views import EventViewSet

# Mapped by hand instead of a DRF router: there's exactly one viewset here,
# and a router would add its own (unwanted) API-root view at this same
# base path.
event_list = EventViewSet.as_view({"get": "list", "post": "create"})
event_detail = EventViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)

urlpatterns = [
    path("", event_list, name="event-list"),
    path("<int:pk>/", event_detail, name="event-detail"),
]
