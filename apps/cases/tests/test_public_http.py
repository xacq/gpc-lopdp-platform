import base64
import tempfile
from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.cases.models import RequestAccessToken, RightsRequest
from apps.cases.services.cases import CaseWorkflowService
from apps.cases.services.tokens import RequestAccessTokenService
from apps.evidence.services.attachments import AttachmentService
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService


ENCRYPTION_KEY = base64.b64encode(b"U" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"V" * 32).decode("ascii")
PDF_BYTES = b"%PDF-1.7\n%%EOF\n"


class CleanScanner:
    def scan(self, content: bytes) -> str:
        return "CLEAN"


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
)
class PublicCaseHttpTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_override = override_settings(
            PRIVATE_STORAGE_ROOT=self.temp_dir.name,
            MEDIA_ROOT="",
            STATIC_ROOT="",
        )
        self.storage_override.enable()
        self.addCleanup(self.storage_override.disable)
        self.addCleanup(self.temp_dir.cleanup)

        SystemSetting.objects.create(
            legal_name="VINOS Y ESPIRITUOSOS VINESA S.A.",
            trade_name="VINESA",
            ruc="1792049598001",
            domain="privacidad.vinesa.test",
            contact_email="privacidad@vinesa.com.ec",
            request_prefix="VINESA",
            timezone="America/Guayaquil",
        )
        right = RightCatalog.objects.create(
            code="PUBLIC_HTTP_TEST",
            name="Derecho público de prueba",
            is_active=True,
        )
        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular HTTP Secreto",
            email="private-http@example.com",
        )
        self.case = CaseWorkflowService.create_request(
            data_subject=subject,
            right=right,
            request_details="Detalle privado de la solicitud",
        )
        self.tracking = RequestAccessTokenService.issue(
            request=self.case,
            purpose=RequestAccessToken.Purpose.TRACKING,
            ttl=timedelta(hours=24),
        )

        actor = get_user_model().objects.create_user(
            email="public-files@example.com",
            password="TestPassword123!",
            full_name="Operador de archivos",
            is_active=True,
        )
        self.attachment = AttachmentService.create(
            request=self.case,
            attachment_type="RESPONSE_DOCUMENT",
            visibility="SUBJECT",
            filename="respuesta.pdf",
            declared_mime="application/pdf",
            content=PDF_BYTES,
            actor=actor,
            scanner=CleanScanner(),
        )
        self.download = RequestAccessTokenService.issue(
            request=self.case,
            purpose=RequestAccessToken.Purpose.FILE_DOWNLOAD,
            ttl=timedelta(minutes=15),
            resource_type=RequestAccessToken.ResourceType.ATTACHMENT,
            resource_id=self.attachment.id,
        )

    def assert_private_headers(self, response):
        self.assertEqual(response["Cache-Control"], "no-store, max-age=0")
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def tracking_post(self, **overrides):
        data = {
            "reference_number": self.case.reference_number,
            "token": self.tracking.token,
        }
        data.update(overrides)
        return self.client.post(reverse("cases:public_tracking"), data)

    def download_post(self, **overrides):
        data = {
            "reference_number": self.case.reference_number,
            "attachment_id": str(self.attachment.id),
            "token": self.download.token,
        }
        data.update(overrides)
        return self.client.post(reverse("cases:public_download"), data)

    def test_public_forms_are_available_without_authentication(self):
        tracking_response = self.client.get(
            reverse("cases:public_tracking")
        )
        download_response = self.client.get(
            reverse("cases:public_download_form")
        )
        self.assertEqual(tracking_response.status_code, 200)
        self.assertEqual(download_response.status_code, 200)
        self.assertContains(tracking_response, "Consulta tu solicitud")
        self.assertNotContains(tracking_response, "novalidate")
        self.assertContains(download_response, "Descargar documento")
        self.assert_private_headers(tracking_response)
        self.assert_private_headers(download_response)

    def test_valid_tracking_displays_only_public_status_data(self):
        response = self.tracking_post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.case.reference_number)
        self.assertContains(response, "Recibida")
        self.assertNotContains(response, self.tracking.token)
        self.assertNotContains(response, "Titular HTTP Secreto")
        self.assertNotContains(response, "private-http@example.com")
        self.assertNotContains(response, "1712345678")
        self.assertNotContains(response, "Detalle privado")
        self.assert_private_headers(response)

    def test_tracking_errors_are_generic_and_do_not_echo_credentials(self):
        invalid_token = "invalid-public-token"
        unknown_reference = "VINESA-2099-999999"

        invalid = self.tracking_post(token=invalid_token)
        unknown = self.tracking_post(reference_number=unknown_reference)
        for response in (invalid, unknown):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "No fue posible consultar")
            self.assertNotContains(response, invalid_token)
            self.assertNotContains(response, unknown_reference)
            self.assertNotContains(response, self.tracking.token)
            self.assert_private_headers(response)

    def test_tracking_requires_reference_and_tracking_code(self):
        response = self.tracking_post(reference_number="", token="")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo es obligatorio", count=2)
        self.assertNotContains(response, "No fue posible consultar la solicitud")
        self.assertNotContains(response, self.tracking.token)
        self.assert_private_headers(response)

    def test_tracking_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("cases:public_tracking"),
            {
                "reference_number": self.case.reference_number,
                "token": self.tracking.token,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_tracking_accepts_csrf_from_http_application_origin(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse("cases:public_tracking")
        client.get(url)

        response = client.post(
            url,
            {
                "reference_number": self.case.reference_number,
                "token": self.tracking.token,
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
            HTTP_ORIGIN="http://testserver",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.case.reference_number)

    def test_download_is_post_only_and_returns_safe_attachment(self):
        get_response = self.client.get(reverse("cases:public_download"))
        self.assertEqual(get_response.status_code, 405)

        response = self.download_post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, PDF_BYTES)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["Content-Length"], str(len(PDF_BYTES)))
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("respuesta.pdf", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assert_private_headers(response)

        self.download.record.refresh_from_db()
        self.assertIsNotNone(self.download.record.revoked_at)

    def test_consumed_download_returns_same_generic_error(self):
        self.download_post()
        response = self.download_post()
        self.assertEqual(response.status_code, 404)
        self.assertContains(
            response,
            "No fue posible descargar",
            status_code=404,
        )
        self.assertNotContains(
            response,
            self.download.token,
            status_code=404,
        )
        self.assert_private_headers(response)

    def test_download_errors_do_not_echo_submitted_credentials(self):
        invalid_token = "invalid-download-token"
        unknown_reference = "VINESA-2099-999999"
        responses = (
            self.download_post(token=invalid_token),
            self.download_post(reference_number=unknown_reference),
            self.download_post(attachment_id=str(uuid.uuid4())),
            self.download_post(attachment_id="not-a-uuid"),
        )

        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertContains(
                response,
                "No fue posible descargar",
                status_code=404,
            )
            self.assertNotContains(
                response,
                invalid_token,
                status_code=404,
            )
            self.assertNotContains(
                response,
                unknown_reference,
                status_code=404,
            )
            self.assertNotContains(
                response,
                self.download.token,
                status_code=404,
            )
            self.assert_private_headers(response)

    def test_download_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("cases:public_download"),
            {
                "reference_number": self.case.reference_number,
                "attachment_id": str(self.attachment.id),
                "token": self.download.token,
            },
        )
        self.assertEqual(response.status_code, 403)
