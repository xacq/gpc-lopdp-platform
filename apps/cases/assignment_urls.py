from django.urls import path

from apps.cases.views.assignments import (
    assignment_apply,
    assignment_history,
    assignment_request_list,
    assignment_summary,
)


app_name = "assignments"


urlpatterns = [
    path("summary/", assignment_summary, name="summary"),
    path("requests/", assignment_request_list, name="request_list"),
    path("history/", assignment_history, name="history"),
    path("apply/", assignment_apply, name="apply"),
]
