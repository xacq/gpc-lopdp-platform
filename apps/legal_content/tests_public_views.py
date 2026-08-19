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
        self.assertContains(response, "Contenido pendiente de aprobación")
        self.assertContains(response, "Borrador editorial temporal")
        self.assertContains(response, "Preliminar · no aprobado")
        self.assertContains(response, "Información a solicitar al cliente")

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
        self.assertNotContains(response, "Borrador editorial temporal")

    def test_legal_index_lists_all_supported_documents_as_pending(self):
        response = self.client.get(reverse("legal_content:public_index"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "legal_content/public_index.html")
        self.assertContains(response, "Avisos y políticas")
        self.assertContains(response, ">Pendiente<", count=8, html=False)
        self.assertContains(response, self.url("privacidad"))
        self.assertContains(response, self.url("cookies"))
        self.assertContains(response, self.url("videovigilancia"))

    def test_legal_index_marks_published_document_as_current(self):
        LegalDocument.objects.create(
            document_type=LegalDocument.DocumentType.COOKIES_POLICY,
            title="Política de Cookies aprobada",
            slug="cookies-aprobada",
            version="1.0",
            content_html="<p>Contenido aprobado.</p>",
            content_sha256="2" * 64,
            effective_from=timezone.now(),
            is_published=True,
        )

        response = self.client.get(reverse("legal_content:public_index"))

        self.assertContains(response, "Política de Cookies aprobada")
        self.assertContains(response, ">Vigente<", count=1, html=False)

    def test_each_empty_document_exposes_client_requirements(self):
        for key in (
            "privacidad",
            "derechos",
            "cookies",
            "empleados",
            "candidatos",
            "clientes-vendedores",
            "proveedores",
            "videovigilancia",
        ):
            with self.subTest(key=key):
                response = self.client.get(self.url(key))
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    "Datos necesarios para completar este documento",
                )
                self.assertContains(response, "Borrador editorial temporal")

    def test_preliminary_document_content_is_specific_to_document_type(self):
        privacy_response = self.client.get(self.url("privacidad"))
        cookies_response = self.client.get(self.url("cookies"))

        self.assertContains(privacy_response, "Compromiso institucional")
        self.assertContains(privacy_response, "selección y contratación")
        self.assertContains(privacy_response, "privacidad@vinesa.com.ec")
        self.assertContains(cookies_response, "Gestión de preferencias")
        self.assertContains(cookies_response, "aceptar, rechazar o personalizar")

    def test_rights_notice_uses_confirmed_corporate_channel(self):
        response = self.client.get(self.url("derechos"))

        self.assertContains(response, "privacidad@vinesa.com.ec")
        self.assertContains(
            response,
            "acceso, rectificación, eliminación y oposición",
        )
        self.assertNotContains(response, "portabilidad, suspensión")
