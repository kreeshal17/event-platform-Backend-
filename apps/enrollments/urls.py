from django.urls import path

from .views import EnrollmentListView

urlpatterns = [
    path("", EnrollmentListView.as_view(), name="enrollment-list"),
]
