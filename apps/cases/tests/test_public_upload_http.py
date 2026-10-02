import base64
import tempfile
import uuid
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.evidence.models import RequestAttachment, TemporaryUpload
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting


ENCRYPTION_KEY = base64.b64encode(b"E" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"F" * 32).decode("ascii")
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
    PUBLIC_UPLOAD_MALWARE_SCANNER=(
        "apps.evidence.tests_temporary_uploads.CleanScanner"
    ),
    PUBLIC_TEMPORARY_UPLOAD_TTL_SECONDS=3600,
)
class PublicUploadHttpTests(TestCase):
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
        self.right = RightCatalog.objects.create(
            code="PUBLIC_UPLOAD_HTTP",
            name="Carga pública HTTP",
            is_active=True,
        )
        self.data = {
            "subject_type": "CUSTOMER",
            "document_type": "CEDULA",
            "document_number": "1700000001",
            "full_name": "Titular con Documento",
            "email": "upload-subject@example.com",
            "phone": "+593 99 000 0001",
            "right": str(self.right.id),
            "request_details": "Solicitud con respaldo privado",
            "has_representative": "",
            "representative_name": "",
            "representative_document_type": "",
            "representative_document_number": "",
            "representative_email": "",
            "privacy_acknowledgement": "on",
            "submission_key": str(uuid.uuid4()),
            "website": "",
        }

    def pdf(self, name="identidad-privada.pdf"):
        return SimpleUploadedFile(
            name,
            PDF_BYTES,
            content_type="application/pdf",
        )

    def test_valid_public_document_is_scanned_encrypted_and_promoted(self):
        data = dict(self.data)
        data["identity_document"] = self.pdf()
        response = self.client.post(
            reverse("cases:public_request_create"), data
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(RightsRequest.objects.count(), 1)
        upload = TemporaryUpload.objects.get()
        attachment = RequestAttachment.objects.get()
        self.assertEqual(upload.status, "PROMOTED")
        self.assertEqual(upload.malware_scan_status, "CLEAN")
        self.assertEqual(attachment.attachment_type, "IDENTITY_DOCUMENT")
        self.assertEqual(attachment.visibility, "INTERNAL")
        self.assertIsNone(attachment.uploaded_by_id)
        physical = Path(self.temp_dir.name) / attachment.storage_key
        self.assertTrue(physical.is_file())
        self.assertNotIn(PDF_BYTES, physical.read_bytes())
        self.assertNotIn("identidad-privada.pdf", response.content.decode())

        serialized_audit = str(
            list(AuditLog.objects.values("description", "metadata"))
        )
        self.assertNotIn("identidad-privada.pdf", serialized_audit)
        self.assertNotIn(attachment.storage_key, serialized_audit)

    def test_repeated_public_document_submission_key_is_ignored(self):
        data = dict(self.data)
        data["identity_document"] = self.pdf()
        first = self.client.post(
            reverse("cases:public_request_create"), data
        )
        repeated = dict(self.data)
        repeated["identity_document"] = self.pdf("identidad-repetida.pdf")
        second = self.client.post(
            reverse("cases:public_request_create"), repeated
        )

        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 303)
        self.assertEqual(RightsRequest.objects.count(), 1)
        self.assertEqual(RequestAttachment.objects.count(), 1)
        self.assertEqual(TemporaryUpload.objects.count(), 1)

    def test_mime_mismatch_is_rejected_without_persistence(self):
        data = dict(self.data)
        data["identity_document"] = SimpleUploadedFile(
            "identidad.png",
            PDF_BYTES,
            content_type="image/png",
        )
        response = self.client.post(
            reverse("cases:public_request_create"), data
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No fue posible aceptar los documentos")
        self.assertContains(response, "25 MB por archivo")
        self.assertFalse(RightsRequest.objects.exists())
        self.assertFalse(TemporaryUpload.objects.exists())
        self.assertFalse(RequestAttachment.objects.exists())
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*.bin")), [])

    @override_settings(
        PUBLIC_UPLOAD_MALWARE_SCANNER=(
            "apps.evidence.services.scanners.ClamAVCommandScanner"
        ),
        CLAMAV_EXECUTABLE="missing-clamscan-command",
    )
    def test_unavailable_malware_scanner_fails_closed(self):
        data = dict(self.data)
        data["supporting_document"] = self.pdf("respaldo.pdf")
        response = self.client.post(
            reverse("cases:public_request_create"), data
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No fue posible aceptar los documentos")
        self.assertContains(response, "25 MB por archivo")
        self.assertFalse(RightsRequest.objects.exists())
        self.assertFalse(TemporaryUpload.objects.exists())

    def test_authority_document_requires_representative_data(self):
        data = dict(self.data)
        data["authority_document"] = self.pdf("representacion.pdf")
        response = self.client.post(
            reverse("cases:public_request_create"), data
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Este documento requiere los datos del representante",
        )
        self.assertFalse(TemporaryUpload.objects.exists())
        self.assertFalse(RightsRequest.objects.exists())

    def test_domain_rejection_discards_staged_encrypted_file(self):
        first = self.client.post(
            reverse("cases:public_request_create"), self.data
        )
        self.assertEqual(first.status_code, 303)

        mismatched = dict(self.data)
        mismatched["submission_key"] = str(uuid.uuid4())
        mismatched["email"] = "different@example.com"
        mismatched["supporting_document"] = self.pdf("evidencia.pdf")
        second = self.client.post(
            reverse("cases:public_request_create"), mismatched
        )

        self.assertEqual(second.status_code, 303)
        self.assertEqual(RightsRequest.objects.count(), 1)
        upload = TemporaryUpload.objects.get()
        self.assertEqual(upload.status, "DELETED")
        self.assertIsNotNone(upload.deleted_at)
        self.assertFalse(RequestAttachment.objects.exists())
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*.bin")), [])
