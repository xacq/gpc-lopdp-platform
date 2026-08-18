import base64
import tempfile
from datetime import timedelta
from pathlib import Path
import uuid

from django.contrib.auth import get_user_model
from django.test import (
    TestCase,
    override_settings,
)

from apps.audit.models import AuditLog
from apps.cases.models import (
    RequestAccessToken,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.cases.services.public_downloads import (
    PublicDownloadAccessError,
    PublicDownloadService,
)
from apps.cases.services.tokens import (
    RequestAccessTokenService,
)
from apps.evidence.services.attachments import (
    AttachmentIntegrityError,
    AttachmentService,
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
    b"S" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"T" * 32
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
class PublicDownloadServiceTests(
    TestCase
):

    def setUp(self):
        self.temp_dir = (
            tempfile
            .TemporaryDirectory()
        )

        self.storage_override = (
            override_settings(
                PRIVATE_STORAGE_ROOT=(
                    self.temp_dir.name
                ),
                MEDIA_ROOT="",
                STATIC_ROOT="",
            )
        )
        self.storage_override.enable()

        self.addCleanup(
            self.storage_override.disable
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

        self.attachment = (
            AttachmentService.create(
                request=self.request,
                attachment_type=(
                    "RESPONSE_DOCUMENT"
                ),
                visibility="SUBJECT",
                filename="respuesta.pdf",
                declared_mime=(
                    "application/pdf"
                ),
                content=PDF_BYTES,
                actor=self.actor,
                scanner=CleanScanner(),
            )
        )

        self.issued = (
            RequestAccessTokenService
            .issue(
                request=self.request,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .FILE_DOWNLOAD
                ),
                ttl=timedelta(
                    minutes=15
                ),
                resource_type=(
                    RequestAccessToken
                    .ResourceType
                    .ATTACHMENT
                ),
                resource_id=(
                    self.attachment.id
                ),
            )
        )

    def download(self):
        return (
            PublicDownloadService
            .download_attachment(
                reference_number=(
                    self.request
                    .reference_number
                ),
                attachment_id=(
                    self.attachment.id
                ),
                token=self.issued.token,
            )
        )

    def test_subject_visible_attachment_can_be_downloaded(self):
        result = self.download()

        self.assertEqual(
            result.content,
            PDF_BYTES,
        )
        self.assertEqual(
            result.filename,
            "respuesta.pdf",
        )
        self.assertEqual(
            result.mime_type,
            "application/pdf",
        )

    def test_download_token_is_consumed(self):
        self.download()

        self.issued.record \
            .refresh_from_db()

        self.assertIsNotNone(
            self.issued.record.revoked_at
        )

        with self.assertRaises(
            PublicDownloadAccessError
        ):
            self.download()

    def test_internal_attachment_is_not_publicly_downloadable(self):
        internal = (
            AttachmentService.create(
                request=self.request,
                attachment_type=(
                    "SUPPORTING_DOCUMENT"
                ),
                visibility="INTERNAL",
                filename="interno.pdf",
                declared_mime=(
                    "application/pdf"
                ),
                content=PDF_BYTES,
                actor=self.actor,
                scanner=CleanScanner(),
            )
        )

        issued = (
            RequestAccessTokenService
            .issue(
                request=self.request,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .FILE_DOWNLOAD
                ),
                ttl=timedelta(
                    minutes=15
                ),
                resource_type=(
                    RequestAccessToken
                    .ResourceType
                    .ATTACHMENT
                ),
                resource_id=internal.id,
            )
        )

        with self.assertRaises(
            PublicDownloadAccessError
        ):
            (
                PublicDownloadService
                .download_attachment(
                    reference_number=(
                        self.request
                        .reference_number
                    ),
                    attachment_id=(
                        internal.id
                    ),
                    token=issued.token,
                )
            )

    def test_token_bound_to_another_attachment_is_rejected(self):
        second = (
            AttachmentService.create(
                request=self.request,
                attachment_type=(
                    "RESPONSE_DOCUMENT"
                ),
                visibility="SUBJECT",
                filename="segunda.pdf",
                declared_mime=(
                    "application/pdf"
                ),
                content=PDF_BYTES,
                actor=self.actor,
                scanner=CleanScanner(),
            )
        )

        with self.assertRaises(
            PublicDownloadAccessError
        ):
            (
                PublicDownloadService
                .download_attachment(
                    reference_number=(
                        self.request
                        .reference_number
                    ),
                    attachment_id=second.id,
                    token=self.issued.token,
                )
            )

    def test_unknown_reference_returns_generic_error(self):
        with self.assertRaises(
            PublicDownloadAccessError
        ):
            (
                PublicDownloadService
                .download_attachment(
                    reference_number=(
                        "VINESA-2099-999999"
                    ),
                    attachment_id=(
                        self.attachment.id
                    ),
                    token=self.issued.token,
                )
            )

    def test_unknown_attachment_returns_generic_error(self):
        with self.assertRaises(
            PublicDownloadAccessError
        ):
            (
                PublicDownloadService
                .download_attachment(
                    reference_number=(
                        self.request
                        .reference_number
                    ),
                    attachment_id=(
                        uuid.uuid4()
                    ),
                    token=self.issued.token,
                )
            )

    def test_tampered_storage_does_not_consume_token(self):
        physical = (
            Path(self.temp_dir.name)
            / self.attachment
            .storage_key
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
            self.download()

        self.issued.record \
            .refresh_from_db()

        self.assertIsNone(
            self.issued.record.revoked_at
        )

    def test_public_download_audit_contains_no_secret_or_filename(self):
        self.download()

        audit = AuditLog.objects.get(
            action=(
                "PUBLIC_ATTACHMENT_DOWNLOADED"
            ),
            entity_pk=str(
                self.attachment.id
            ),
        )

        serialized = str(
            {
                "metadata": (
                    audit.metadata
                ),
                "description": (
                    audit.description
                ),
            }
        )

        self.assertNotIn(
            self.issued.token,
            serialized,
        )
        self.assertNotIn(
            "respuesta.pdf",
            serialized,
        )
        self.assertNotIn(
            self.attachment.storage_key,
            serialized,
        )
