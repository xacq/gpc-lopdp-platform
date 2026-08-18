import base64
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import (
    TestCase,
    override_settings,
)

from apps.accounts.models import (
    Role,
    UserRole,
)
from apps.cases.models import (
    RequestAccessToken,
    RightsRequest,
)
from apps.cases.services.cases import (
    CasePermissionError,
    CaseWorkflowService,
)
from apps.cases.services.public_downloads import (
    PublicDownloadAccessError,
    PublicDownloadService,
)
from apps.cases.services.public_tracking import (
    PublicTrackingAccessError,
    PublicTrackingService,
)
from apps.cases.services.tokens import (
    RequestAccessTokenService,
)
from apps.communications.models import (
    RequestCommunication,
)
from apps.communications.services.notifications import (
    NotificationService,
)
from apps.evidence.services.attachments import (
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
    b"E" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"F" * 32
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
    EMAIL_BACKEND=(
        "django.core.mail.backends."
        "locmem.EmailBackend"
    ),
    DEFAULT_FROM_EMAIL=(
        "noreply@example.test"
    ),
)
class SecurityRegressionTests(
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
                    "Solicitud sensible"
                ),
            )
        )

        self.manager = (
            self.create_user_with_role(
                email=(
                    "manager@example.com"
                ),
                role_code=(
                    Role.Code.RESPONSABLE
                ),
            )
        )

        self.operator = (
            self.create_user_with_role(
                email=(
                    "operator@example.com"
                ),
                role_code=(
                    Role.Code.OPERADOR
                ),
            )
        )

    def create_user_with_role(
        self,
        *,
        email,
        role_code,
    ):
        user_model = get_user_model()

        user = user_model.objects.create_user(
            email=email,
            password="TestPassword123!",
            full_name="Usuario Prueba",
            is_active=True,
        )

        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={
                "name": role_code,
                "is_active": True,
            },
        )

        UserRole.objects.create(
            user=user,
            role=role,
            is_primary=True,
        )

        return user

    def test_invalid_tracking_token_returns_generic_error(self):
        with self.assertRaises(
            PublicTrackingAccessError
        ):
            (
                PublicTrackingService
                .get_status(
                    reference_number=(
                        self.request
                        .reference_number
                    ),
                    token="invalid-token",
                )
            )

    def test_unknown_reference_returns_same_public_tracking_error(self):
        with self.assertRaises(
            PublicTrackingAccessError
        ):
            (
                PublicTrackingService
                .get_status(
                    reference_number=(
                        "VINESA-2099-999999"
                    ),
                    token="invalid-token",
                )
            )

    def test_operator_cannot_assign_case(self):
        with self.assertRaises(
            CasePermissionError
        ):
            (
                CaseWorkflowService.assign(
                    request=self.request,
                    assignee=self.operator,
                    actor=self.operator,
                )
            )

        self.request.refresh_from_db()

        self.assertIsNone(
            self.request.assigned_to_id
        )

    def test_public_download_rejects_internal_attachment(self):
        attachment = (
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
                actor=self.manager,
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
                resource_id=(
                    attachment.id
                ),
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
                        attachment.id
                    ),
                    token=issued.token,
                )
            )

    def test_public_download_rejects_deleted_attachment(self):
        attachment = (
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
                actor=self.manager,
                scanner=CleanScanner(),
            )
        )

        attachment.deleted_at = (
            self.request.created_at
            + timedelta(seconds=1)
        )
        attachment.save(
            update_fields=[
                "deleted_at",
            ]
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
                resource_id=(
                    attachment.id
                ),
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
                        attachment.id
                    ),
                    token=issued.token,
                )
            )

    def test_notification_database_never_contains_plaintext_payload(self):
        communication = (
            NotificationService
            .queue_email(
                request=self.request,
                communication_type=(
                    "ACKNOWLEDGEMENT"
                ),
                recipient=(
                    "subject@example.com"
                ),
                subject=(
                    "Solicitud sensible"
                ),
                body=(
                    "Documento 1712345678"
                ),
                visible_to_subject=True,
            )
        )

        raw = (
            RequestCommunication.objects
            .values(
                "recipient_encrypted",
                "subject_encrypted",
                "body_encrypted",
            )
            .get(pk=communication.pk)
        )

        serialized = repr(raw)

        self.assertNotIn(
            "subject@example.com",
            serialized,
        )

        self.assertNotIn(
            "Solicitud sensible",
            serialized,
        )

        self.assertNotIn(
            "1712345678",
            serialized,
        )

    def test_tracking_token_cannot_download_attachment(self):
        attachment = (
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
                actor=self.manager,
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
                    .TRACKING
                ),
                ttl=timedelta(
                    minutes=15
                ),
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
                        attachment.id
                    ),
                    token=issued.token,
                )
            )

    def test_file_download_token_cannot_access_tracking(self):
        attachment = (
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
                actor=self.manager,
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
                resource_id=(
                    attachment.id
                ),
            )
        )

        with self.assertRaises(
            PublicTrackingAccessError
        ):
            (
                PublicTrackingService
                .get_status(
                    reference_number=(
                        self.request
                        .reference_number
                    ),
                    token=issued.token,
                )
            )
