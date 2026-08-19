from django.urls import path

from apps.legal_content.views import public_legal_document


app_name = "legal_content"


urlpatterns = [
    path("<slug:document_key>/", public_legal_document, name="public_document"),
]
