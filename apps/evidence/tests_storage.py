import base64
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import (
    TestCase,
    override_settings,
)

from apps.audit.models import AuditLog
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.core.services.storage import (
    LocalPrivateStorageService,
    StorageConfigurationError,
    UnsafeStorageKeyError,
)
from apps.evidence.models import (
    RequestAttachment,
)
from apps.evidence.services.attachments import (
    AttachmentIntegrityError,
    AttachmentLimitError,
    AttachmentService,
    FileRejectedError,
)
from apps.legal_content.models import (
    RightCatalog,
)
from apps.organization.models import (
    SystemSetting,
)
from apps.subjects.services.subjects import (
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"M" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"N" * 32
).decode("ascii")

PDF_BYTES = (
    b"%PDF-1.7\n"
    b"1 0 obj\n"
    b"<< /Type /Catalog >>\n"
    b"endobj\n"
    b"%%EOF\n"
)


class CleanScanner:
    def scan(
        self,
        content: bytes,
    ) -> str:
        return "CLEAN"


class InfectedScanner:
    def scan(
        self,
        content: bytes,
    ) -> str:
        return "INFECTED"


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={
        1: ENCRYPTION_KEY,
    },
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={
        1: LOOKUP_KEY,
    },
)
class AttachmentServiceTests(
    TestCase
):

    def setUp(self):
        self.temp_dir = (
            tempfile
            .TemporaryDirectory()
        )

        self.override_storage = (
            override_settings(
                PRIVATE_STORAGE_ROOT=(
                    self.temp_dir.name
                ),
                MEDIA_ROOT="",
                STATIC_ROOT="",
            )
        )
        self.override_storage.enable()

        self.addCleanup(
            self.override_storage.disable
        )
        self.addCleanup(
            self.temp_dir.cleanup
        )

        SystemSetting.objects.create(
            legal_name=(
                "VINOS Y ESPIRITUOSOS "
                "VINESA S.A."
            ),
            trade_name="VINESA",
            ruc="1792049598001",
            domain=(
                "privacidad.vinesa.test"
            ),
            contact_email=(
                "privacidad@vinesa.com.ec"
            ),
            request_prefix="VINESA",
            timezone=(
                "America/Guayaquil"
            ),
        )

        self.right = (
            RightCatalog.objects.create(
                code="TEST_RIGHT",
                name="Derecho de prueba",
                is_active=True,
            )
        )

        self.subject = (
            SubjectService.create(
                subject_type="CUSTOMER",
                document_type="CEDULA",
                document_number=(
                    "1712345678"
                ),
                full_name=(
                    "Titular Prueba"
                ),
                email=(
                    "subject@example.com"
                ),
            )
        )

        self.request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details=(
                    "Solicitud de prueba"
                ),
            )
        )

        user_model = get_user_model()

        self.actor = (
            user_model.objects
            .create_user(
                email=(
                    "files@example.com"
                ),
                password=(
                    "TestPassword123!"
                ),
                full_name=(
                    "Operador Archivos"
                ),
                is_active=True,
            )
        )

    def create_attachment(
        self,
        *,
        filename="documento.pdf",
        declared_mime=(
            "application/pdf"
        ),
        content=PDF_BYTES,
        scanner=None,
    ):
        return AttachmentService.create(
            request=self.request,
            attachment_type=(
                "SUPPORTING_DOCUMENT"
            ),
            visibility="INTERNAL",
            filename=filename,
            declared_mime=declared_mime,
            content=content,
            actor=self.actor,
            scanner=(
                scanner
                or CleanScanner()
            ),
        )

    def test_private_storage_encrypts_file_bytes(self):
        attachment = (
            self.create_attachment()
        )

        physical = (
            Path(self.temp_dir.name)
            / attachment.storage_key
        )

        raw_on_disk = (
            physical.read_bytes()
        )

        self.assertNotEqual(
            raw_on_disk,
            PDF_BYTES,
        )

        self.assertNotIn(
            PDF_BYTES,
            raw_on_disk,
        )

    def test_attachment_metadata_is_persisted(self):
        attachment = (
            self.create_attachment()
        )

        self.assertEqual(
            attachment.storage_backend,
            "LOCAL",
        )
        self.assertEqual(
            attachment.mime_type,
            "application/pdf",
        )
        self.assertEqual(
            attachment.size_bytes,
            len(PDF_BYTES),
        )
        self.assertEqual(
            len(attachment.file_sha256),
            64,
        )
        self.assertTrue(
            attachment.is_encrypted
        )
        self.assertEqual(
            attachment
            .malware_scan_status,
            "CLEAN",
        )

    def test_original_filename_is_encrypted(self):
        filename = (
            "cedula-persona.pdf"
        )

        attachment = (
            self.create_attachment(
                filename=filename
            )
        )

        self.assertNotIn(
            filename.encode("utf-8"),
            bytes(
                attachment
                .original_filename_encrypted
            ),
        )

        self.assertEqual(
            AttachmentService
            .decrypt_filename(
                attachment
            ),
            filename,
        )

    def test_download_returns_original_content(self):
        attachment = (
            self.create_attachment()
        )

        result = (
            AttachmentService.download(
                attachment=attachment,
                actor=self.actor,
            )
        )

        self.assertEqual(
            result.content,
            PDF_BYTES,
        )
        self.assertEqual(
            result.filename,
            "documento.pdf",
        )

    def test_extension_mime_and_content_must_match(self):
        with self.assertRaises(
            FileRejectedError
        ):
            self.create_attachment(
                filename="documento.png",
                declared_mime=(
                    "image/png"
                ),
                content=PDF_BYTES,
            )

        self.assertEqual(
            RequestAttachment.objects.count(),
            0,
        )

    def test_executable_extension_is_rejected(self):
        with self.assertRaises(
            FileRejectedError
        ):
            self.create_attachment(
                filename="archivo.exe",
                declared_mime=(
                    "application/octet-stream"
                ),
            )

    def test_file_larger_than_10mb_is_rejected(self):
        content = (
            b"%PDF-"
            + b"x" * (
                AttachmentService
                .MAX_FILE_SIZE
            )
        )

        with self.assertRaises(
            FileRejectedError
        ):
            self.create_attachment(
                content=content
            )

    def test_infected_file_is_not_persisted(self):
        with self.assertRaises(
            FileRejectedError
        ):
            self.create_attachment(
                scanner=(
                    InfectedScanner()
                )
            )

        self.assertEqual(
            RequestAttachment.objects.count(),
            0,
        )

        files = list(
            Path(
                self.temp_dir.name
            ).rglob("*.bin")
        )

        self.assertEqual(
            files,
            [],
        )

    def test_maximum_five_active_attachments(self):
        for index in range(5):
            self.create_attachment(
                filename=(
                    f"documento-{index}.pdf"
                )
            )

        with self.assertRaises(
            AttachmentLimitError
        ):
            self.create_attachment(
                filename=(
                    "documento-6.pdf"
                )
            )

        self.assertEqual(
            RequestAttachment.objects.count(),
            5,
        )

    def test_limit_failure_removes_orphan_storage_object(self):
        for index in range(5):
            self.create_attachment(
                filename=(
                    f"documento-{index}.pdf"
                )
            )

        before = set(
            Path(
                self.temp_dir.name
            ).rglob("*.bin")
        )

        with self.assertRaises(
            AttachmentLimitError
        ):
            self.create_attachment(
                filename=(
                    "documento-extra.pdf"
                )
            )

        after = set(
            Path(
                self.temp_dir.name
            ).rglob("*.bin")
        )

        self.assertEqual(
            before,
            after,
        )

    def test_tampered_file_is_detected(self):
        attachment = (
            self.create_attachment()
        )

        physical = (
            Path(self.temp_dir.name)
            / attachment.storage_key
        )

        encrypted = bytearray(
            physical.read_bytes()
        )
        encrypted[-1] ^= 1
        physical.write_bytes(
            bytes(encrypted)
        )

        with self.assertRaises(
            Exception
        ):
            AttachmentService.download(
                attachment=attachment,
                actor=self.actor,
            )

    def test_audit_does_not_store_filename_or_storage_key(self):
        filename = (
            "persona-identificable.pdf"
        )

        attachment = (
            self.create_attachment(
                filename=filename
            )
        )

        audit = AuditLog.objects.get(
            action=(
                "REQUEST_ATTACHMENT_CREATED"
            ),
            entity_pk=str(
                attachment.id
            ),
        )

        serialized = str(
            audit.metadata
        )

        self.assertNotIn(
            filename,
            serialized,
        )
        self.assertNotIn(
            attachment.storage_key,
            serialized,
        )

    def test_storage_key_path_traversal_is_rejected(self):
        with self.assertRaises(
            UnsafeStorageKeyError
        ):
            (
                LocalPrivateStorageService
                .write_encrypted(
                    storage_key=(
                        "../escape.bin"
                    ),
                    plaintext=b"data",
                    key_version=1,
                )
            )

    def test_private_storage_cannot_be_under_media_root(self):
        nested = (
            Path(self.temp_dir.name)
            / "media"
            / "private"
        )

        with override_settings(
            MEDIA_ROOT=(
                Path(self.temp_dir.name)
                / "media"
            ),
            PRIVATE_STORAGE_ROOT=(
                nested
            ),
        ):
            with self.assertRaises(
                StorageConfigurationError
            ):
                (
                    LocalPrivateStorageService
                    .exists(
                        storage_key=(
                            "test/file.bin"
                        )
                    )
                )
