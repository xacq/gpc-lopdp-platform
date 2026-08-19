import base64
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.cases.services.cases import CaseWorkflowService
from apps.evidence.models import RequestAttachment, TemporaryUpload
from apps.evidence.services.attachments import (
    AttachmentLimitError,
    AttachmentService,
    FileRejectedError,
)
from apps.evidence.services.scanners import ClamAVCommandScanner
from apps.evidence.services.temporary_uploads import (
    TemporaryUploadAccessError,
    TemporaryUploadService,
)
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService


ENCRYPTION_KEY = base64.b64encode(b"C" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"D" * 32).decode("ascii")
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


class CleanScanner:
    def scan(self, content: bytes) -> str:
        return "CLEAN"


class InfectedScanner:
    def scan(self, content: bytes) -> str:
        return "INFECTED"


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
    PUBLIC_TEMPORARY_UPLOAD_TTL_SECONDS=3600,
)
class TemporaryUploadServiceTests(TestCase):
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
            code="TEMP_UPLOAD_TEST",
            name="Carga temporal",
            is_active=True,
        )
        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Temporal",
            email="temporary@example.com",
        )
        self.case = CaseWorkflowService.create_request(
            data_subject=subject,
            right=right,
            request_details="Solicitud temporal",
        )
        self.session_key = "private-session-key"

    def create_upload(self, **overrides):
        values = {
            "session_key": self.session_key,
            "attachment_type": "IDENTITY_DOCUMENT",
            "filename": "identidad.pdf",
            "declared_mime": "application/pdf",
            "content": PDF_BYTES,
            "scanner": CleanScanner(),
        }
        values.update(overrides)
        return TemporaryUploadService.create(**values)

    def test_create_encrypts_content_filename_session_and_token(self):
        issued = self.create_upload()
        physical = Path(self.temp_dir.name) / issued.record.storage_key
        stored = physical.read_bytes()

        self.assertNotIn(PDF_BYTES, stored)
        self.assertNotIn(b"identidad.pdf", issued.record.original_filename_encrypted)
        self.assertNotEqual(issued.record.session_key_hash, self.session_key)
        self.assertNotEqual(issued.record.upload_token_hash, issued.token)
        self.assertEqual(issued.record.malware_scan_status, "CLEAN")
        self.assertEqual(issued.record.status, "UPLOADED")

        audit = AuditLog.objects.get(
            action="PUBLIC_TEMPORARY_UPLOAD_CREATED",
            entity_pk=str(issued.record.id),
        )
        serialized = str(audit.metadata)
        self.assertNotIn("identidad.pdf", serialized)
        self.assertNotIn(issued.token, serialized)
        self.assertNotIn(self.session_key, serialized)
        self.assertNotIn(issued.record.storage_key, serialized)

    def test_invalid_or_infected_file_is_not_persisted(self):
        with self.assertRaises(FileRejectedError):
            self.create_upload(
                filename="identidad.png",
                declared_mime="image/png",
            )
        with self.assertRaises(FileRejectedError):
            self.create_upload(scanner=InfectedScanner())

        self.assertFalse(TemporaryUpload.objects.exists())
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*.bin")), [])

    def test_promote_requires_matching_session_and_token(self):
        issued = self.create_upload()
        with self.assertRaises(TemporaryUploadAccessError):
            TemporaryUploadService.promote(
                request=self.case,
                upload_id=issued.record.id,
                token="wrong-token",
                session_key=self.session_key,
            )
        with self.assertRaises(TemporaryUploadAccessError):
            TemporaryUploadService.promote(
                request=self.case,
                upload_id=issued.record.id,
                token=issued.token,
                session_key="wrong-session",
            )
        self.assertFalse(RequestAttachment.objects.exists())

    def test_promote_creates_private_attachment_without_copying_plaintext(self):
        issued = self.create_upload()
        attachment = TemporaryUploadService.promote(
            request=self.case,
            upload_id=issued.record.id,
            token=issued.token,
            session_key=self.session_key,
        )

        issued.record.refresh_from_db()
        self.assertEqual(issued.record.status, "PROMOTED")
        self.assertEqual(issued.record.promoted_request_id, self.case.id)
        self.assertEqual(issued.record.promoted_attachment_id, attachment.id)
        self.assertEqual(attachment.visibility, "INTERNAL")
        self.assertIsNone(attachment.uploaded_by_id)
        self.assertEqual(attachment.storage_key, issued.record.storage_key)
        self.assertEqual(
            AttachmentService.decrypt_filename(attachment), "identidad.pdf"
        )
        physical = Path(self.temp_dir.name) / attachment.storage_key
        self.assertNotIn(PDF_BYTES, physical.read_bytes())

        with self.assertRaises(TemporaryUploadAccessError):
            TemporaryUploadService.promote(
                request=self.case,
                upload_id=issued.record.id,
                token=issued.token,
                session_key=self.session_key,
            )

    def test_expired_upload_cannot_be_promoted(self):
        issued = self.create_upload()
        now = TemporaryUploadService._database_now()
        TemporaryUpload.objects.filter(pk=issued.record.pk).update(
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        with self.assertRaises(TemporaryUploadAccessError):
            TemporaryUploadService.promote(
                request=self.case,
                upload_id=issued.record.id,
                token=issued.token,
                session_key=self.session_key,
            )

    def test_session_limit_is_enforced(self):
        for index in range(AttachmentService.MAX_ATTACHMENTS_PER_REQUEST):
            self.create_upload(filename=f"documento-{index}.pdf")
        before = set(Path(self.temp_dir.name).rglob("*.bin"))

        with self.assertRaises(AttachmentLimitError):
            self.create_upload(filename="documento-extra.pdf")

        self.assertEqual(
            TemporaryUpload.objects.filter(status="UPLOADED").count(), 5
        )
        self.assertEqual(before, set(Path(self.temp_dir.name).rglob("*.bin")))

    def test_cleanup_deletes_only_expired_unpromoted_storage(self):
        expired = self.create_upload(filename="expired-private.pdf")
        promoted = self.create_upload(filename="promoted-private.pdf")
        attachment = TemporaryUploadService.promote(
            request=self.case,
            upload_id=promoted.record.id,
            token=promoted.token,
            session_key=self.session_key,
        )
        now = TemporaryUploadService._database_now()
        TemporaryUpload.objects.filter(pk=expired.record.pk).update(
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        output = StringIO()

        call_command(
            "cleanup_temporary_uploads",
            batch_size=100,
            stdout=output,
            no_color=True,
        )

        expired.record.refresh_from_db()
        self.assertEqual(expired.record.status, "EXPIRED")
        self.assertIsNotNone(expired.record.deleted_at)
        self.assertFalse(
            (Path(self.temp_dir.name) / expired.record.storage_key).exists()
        )
        self.assertTrue(
            (Path(self.temp_dir.name) / attachment.storage_key).exists()
        )
        rendered = output.getvalue()
        self.assertIn("eliminados=1", rendered)
        self.assertNotIn("expired-private.pdf", rendered)
        self.assertNotIn(expired.token, rendered)
        self.assertNotIn(self.session_key, rendered)

    @override_settings(CLAMAV_EXECUTABLE="missing-clamscan-command")
    def test_clamav_scanner_fails_closed_when_unavailable(self):
        self.assertEqual(ClamAVCommandScanner().scan(PDF_BYTES), "FAILED")
