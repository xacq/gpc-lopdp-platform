from django.urls import path

from apps.cases.views import (
    request_assign,
    request_clarification_create,
    request_clarification_receive,
    request_create,
    request_detail,
    request_list,
    request_start_review,
)


app_name = "cases"


urlpatterns = [
    path(
        "",
        request_list,
        name="request_list",
    ),
    path(
        "new/",
        request_create,
        name="request_create",
    ),
    path(
        "<uuid:request_id>/",
        request_detail,
        name="request_detail",
    ),
    path(
        "<uuid:request_id>/assign/",
        request_assign,
        name="request_assign",
    ),
    path(
        (
            "<uuid:request_id>/"
            "start-review/"
        ),
        request_start_review,
        name="request_start_review",
    ),
    path(
        (
            "<uuid:request_id>/"
            "clarifications/new/"
        ),
        request_clarification_create,
        name=(
            "request_clarification_create"
        ),
    ),
    path(
        (
            "<uuid:request_id>/"
            "clarifications/"
            "<uuid:clarification_id>/"
            "receive/"
        ),
        request_clarification_receive,
        name=(
            "request_clarification_receive"
        ),
    ),
]
