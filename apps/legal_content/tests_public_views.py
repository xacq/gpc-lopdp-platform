from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.legal_content.models import LegalDocument


class PublicLegalDocumentTests(TestCase):
    def url(self, key="privacidad"):
        return reverse("legal_content:public_document", args=[key])

    def test_unknown_document_key_returns_404(self):
        self.assertEqual(self.client.get(self.url("desconocido")).status_code, 404)

    def test_draft_content_is_never_exposed(self):
        LegalDocument.objects.create(
            document_type=LegalDocument.DocumentType.PRIVACY_POLICY,
            title="Borrador confidencial",
            slug="borrador-confidencial",
            version="0.1",
            content_html="<p>No publicar</p>",
            content_sha256="0" * 64,
            effective_from=timezone.now(),
            is_published=False,
        )
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "No publicar")
        self.assertContains(response, "Contenido en actualización")

    def test_current_published_document_is_rendered(self):
        LegalDocument.objects.create(
            document_type=LegalDocument.DocumentType.PRIVACY_POLICY,
            title="Política de Privacidad VINESA",
            slug="politica-privacidad",
            version="1.0",
            content_html="<h2>Responsable del tratamiento</h2><p>Contenido público.</p>",
            content_sha256="1" * 64,
            effective_from=timezone.now(),
            is_published=True,
        )
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Responsable del tratamiento")
        self.assertContains(response, "Contenido público.")
