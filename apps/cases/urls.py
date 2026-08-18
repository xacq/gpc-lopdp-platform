from django.urls import path

from apps.cases.views import (
    request_assign,
    request_clarification_create,
    request_clarification_receive,
    request_create,
    request_detail,
    request_extension,
    request_list,
    request_mark_responded,
    request_resolution,
    request_close,
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
            "extension/"
        ),
        request_extension,
        name="request_extension",
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
    path(
        (
            "<uuid:request_id>/"
            "resolution/"
        ),
        request_resolution,
        name="request_resolution",
    ),
    path(
        (
            "<uuid:request_id>/"
            "mark-responded/"
        ),
        request_mark_responded,
        name="request_mark_responded",
    ),
    path(
        (
            "<uuid:request_id>/"
            "close/"
        ),
        request_close,
        name="request_close",
    ),

]
