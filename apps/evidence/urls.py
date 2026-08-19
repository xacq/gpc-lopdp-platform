from django.urls import path

from apps.evidence.views import (
    attachment_download,
    attachment_list,
    identity_verification_create,
    identity_verification_list,
)


app_name = "evidence"


urlpatterns = [
    path("identity/", identity_verification_list, name="identity_list"),
    path(
        "identity/record/",
        identity_verification_create,
        name="identity_create",
    ),
    path("attachments/", attachment_list, name="attachment_list"),
    path(
        "attachments/<uuid:attachment_id>/download/",
        attachment_download,
        name="attachment_download",
    ),
]
