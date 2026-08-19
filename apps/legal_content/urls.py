from django.urls import path

from apps.legal_content.views import (
    legal_document_create,
    legal_document_list,
    legal_document_panel,
    legal_document_publish,
    public_legal_document,
    public_legal_index,
)


app_name = "legal_content"


urlpatterns = [
    path("manage/", legal_document_panel, name="manage_panel"),
    path("manage/documents/", legal_document_list, name="manage_list"),
    path("manage/documents/create/", legal_document_create, name="manage_create"),
    path(
        "manage/documents/<uuid:document_id>/publish/",
        legal_document_publish,
        name="manage_publish",
    ),
    path("", public_legal_index, name="public_index"),
    path("<slug:document_key>/", public_legal_document, name="public_document"),
]
