from django.urls import path

from apps.legal_content.views import public_legal_document, public_legal_index


app_name = "legal_content"


urlpatterns = [
    path("", public_legal_index, name="public_index"),
    path("<slug:document_key>/", public_legal_document, name="public_document"),
]
