import base64
import tempfile
from datetime import timedelta

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
    RequestResolution,
    RightsRequest,
)
from apps.cases.services.cases import (
    CasePermissionError,
    CaseWorkflowService,
)
from apps.cases.services.deadlines import (
    DeadlineService,
)
from apps.cases.services.public_downloads import (
    PublicDownloadAccessError,
    PublicDownloadService,
)
from apps.cases.services.public_tracking import (
    PublicTrackingService,
)
from apps.cases.services.resolutions import (
    ResolutionService,
)
from apps.cases.services.tokens import (
    RequestAccessTokenService,
)
from apps.communications.services.notifications import (
    NotificationService,
)
from apps.evidence.services.attachments import (
    AttachmentService,
)
from apps.legal_content.models import (
    RightCatalog,
    RightRule,
)
from apps.organization.models import (
    SystemSetting,
)
from apps.subjects.services.subjects import (
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"U" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"V" * 32
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
class CaseEndToEndTests(TestCase):

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

        self.rule = (
            RightRule.objects.create(
                right=self.right,
                response_days=5,
                day_count_type=(
                    RightRule
                    .DayCountType
                    .BUSINESS
                ),
                extension_allowed=True,
                extension_days=3,
                warning_days=2,
                clarification_effect=(
                    RightRule
                    .ClarificationEffect
                    .NO_CHANGE
                ),
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

    def create_request(self):
        return (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details=(
                    "Solicitud integral "
                    "de prueba"
                ),
            )
        )

    def start_assigned_review(
        self,
        request,
    ):
        request = (
            CaseWorkflowService.assign(
                request=request,
                assignee=self.operator,
                actor=self.manager,
            )
        )

        return (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=self.operator,
            )
        )

    def test_full_approved_case_can_close_and_be_tracked(self):
        request = self.create_request()

        tracking = (
            RequestAccessTokenService
            .issue(
                request=request,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .TRACKING
                ),
                ttl=timedelta(
                    hours=24
                ),
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        request = self.start_assigned_review(
            request
        )

        clarification = (
            CaseWorkflowService
            .request_clarification(
                request=request,
                message=(
                    "Complete la información."
                ),
                actor=self.operator,
            )
        )

        CaseWorkflowService \
            .receive_clarification(
                clarification=(
                    clarification
                ),
                response_message=(
                    "Información completada."
                ),
                actor=self.operator,
            )

        request.refresh_from_db()

        ResolutionService.approve(
            request=request,
            details=(
                "Solicitud aprobada."
            ),
            actor=self.manager,
        )

        request = (
            ResolutionService
            .mark_responded(
                request=request,
                actor=self.manager,
            )
        )

        request = (
            ResolutionService.close(
                request=request,
                actor=self.manager,
            )
        )

        result = (
            PublicTrackingService
            .get_status(
                reference_number=(
                    request.reference_number
                ),
                token=tracking.token,
            )
        )

        self.assertEqual(
            request.status,
            RightsRequest.Status.CLOSED,
        )

        self.assertEqual(
            result.status,
            RightsRequest.Status.CLOSED,
        )

        self.assertIsNotNone(
            request.responded_at
        )

        self.assertIsNotNone(
            request.closed_at
        )

    def test_extension_then_approval_flow_completes(self):
        request = self.create_request()

        DeadlineService.initialize_initial(
            request=request
        )

        request = self.start_assigned_review(
            request
        )

        extension = (
            CaseWorkflowService
            .apply_extension(
                request=request,
                reason=(
                    "Complejidad técnica."
                ),
                actor=self.manager,
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest.Status.EXTENDED,
        )

        self.assertEqual(
            request.current_due_at,
            extension.due_at,
        )

        ResolutionService.approve(
            request=request,
            details=(
                "Aprobada luego de extensión."
            ),
            actor=self.manager,
        )

        request = (
            ResolutionService
            .mark_responded(
                request=request,
                actor=self.manager,
            )
        )

        request = (
            ResolutionService.close(
                request=request,
                actor=self.manager,
            )
        )

        self.assertEqual(
            request.status,
            RightsRequest.Status.CLOSED,
        )

    def test_public_response_document_download_is_single_use(self):
        request = self.create_request()

        attachment = (
            AttachmentService.create(
                request=request,
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
                request=request,
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

        downloaded = (
            PublicDownloadService
            .download_attachment(
                reference_number=(
                    request.reference_number
                ),
                attachment_id=(
                    attachment.id
                ),
                token=issued.token,
            )
        )

        self.assertEqual(
            downloaded.content,
            PDF_BYTES,
        )

        with self.assertRaises(
            PublicDownloadAccessError
        ):
            (
                PublicDownloadService
                .download_attachment(
                    reference_number=(
                        request
                        .reference_number
                    ),
                    attachment_id=(
                        attachment.id
                    ),
                    token=issued.token,
                )
            )

    def test_acknowledgement_notification_can_be_sent(self):
        request = self.create_request()

        communication = (
            NotificationService
            .queue_email(
                request=request,
                communication_type=(
                    "ACKNOWLEDGEMENT"
                ),
                recipient=(
                    "subject@example.com"
                ),
                subject=(
                    "Solicitud recibida"
                ),
                body=(
                    "Su solicitud fue recibida."
                ),
                visible_to_subject=True,
            )
        )

        communication = (
            NotificationService
            .process_email(
                communication.id
            )
        )

        communication.refresh_from_db()

        self.assertEqual(
            communication.delivery_status,
            "SENT",
        )

        self.assertIsNotNone(
            communication.sent_at
        )

    def test_operator_can_process_case_but_cannot_resolve(self):
        request = self.create_request()

        DeadlineService.initialize_initial(
            request=request
        )

        request = self.start_assigned_review(
            request
        )

        clarification = (
            CaseWorkflowService
            .request_clarification(
                request=request,
                message="Aclare.",
                actor=self.operator,
            )
        )

        CaseWorkflowService \
            .receive_clarification(
                clarification=(
                    clarification
                ),
                response_message=(
                    "Respuesta."
                ),
                actor=self.operator,
            )

        request.refresh_from_db()

        with self.assertRaises(
            CasePermissionError
        ):
            ResolutionService.approve(
                request=request,
                details=(
                    "No autorizado."
                ),
                actor=self.operator,
            )

        self.assertFalse(
            RequestResolution.objects
            .filter(request=request)
            .exists()
        )

    def test_tracking_result_never_exposes_subject_pii(self):
        request = self.create_request()

        issued = (
            RequestAccessTokenService
            .issue(
                request=request,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .TRACKING
                ),
                ttl=timedelta(
                    hours=24
                ),
            )
        )

        result = (
            PublicTrackingService
            .get_status(
                reference_number=(
                    request.reference_number
                ),
                token=issued.token,
            )
        )

        serialized = str(result)

        self.assertNotIn(
            "Titular Prueba",
            serialized,
        )
        self.assertNotIn(
            "subject@example.com",
            serialized,
        )
        self.assertNotIn(
            "1712345678",
            serialized,
        )
        self.assertNotIn(
            "Solicitud integral de prueba",
            serialized,
        )
