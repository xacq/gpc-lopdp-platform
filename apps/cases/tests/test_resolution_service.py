import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import (
    Role,
    UserRole,
)
from apps.audit.models import AuditLog
from apps.cases.models import (
    CaseOutcomeReason,
    RequestClarification,
    RequestDeadline,
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
from apps.cases.services.resolutions import (
    ResolutionCloseBlockedError,
    ResolutionConflictError,
    ResolutionReasonError,
    ResolutionService,
    ResolutionStateError,
)
from apps.legal_content.models import (
    RightCatalog,
    RightRule,
)
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import (
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"I" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"J" * 32
).decode("ascii")


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
class ResolutionServiceTests(TestCase):

    def setUp(self):
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
                email="manager@example.com",
                role_code=(
                    Role.Code.RESPONSABLE
                ),
            )
        )

        self.operator = (
            self.create_user_with_role(
                email="operator@example.com",
                role_code=(
                    Role.Code.OPERADOR
                ),
            )
        )

        self.rejection_reason = (
            CaseOutcomeReason.objects
            .create(
                reason_type=(
                    CaseOutcomeReason
                    .ReasonType
                    .REJECTION
                ),
                code="TEST_REJECTION",
                name=(
                    "Causal de rechazo "
                    "de prueba"
                ),
                is_active=True,
            )
        )

        self.archive_reason = (
            CaseOutcomeReason.objects
            .create(
                reason_type=(
                    CaseOutcomeReason
                    .ReasonType
                    .ARCHIVE
                ),
                code="TEST_ARCHIVE",
                name=(
                    "Causal de archivo "
                    "de prueba"
                ),
                is_active=True,
            )
        )

        self.cancel_reason = (
            CaseOutcomeReason.objects
            .create(
                reason_type=(
                    CaseOutcomeReason
                    .ReasonType
                    .CANCELLATION
                ),
                code="TEST_CANCEL",
                name=(
                    "Causal de cancelación "
                    "de prueba"
                ),
                is_active=True,
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

    def create_request(
        self,
        *,
        start_review=True,
        initialize_deadline=True,
    ):
        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details=(
                    "Solicitud de prueba"
                ),
            )
        )

        if initialize_deadline:
            DeadlineService \
                .initialize_initial(
                    request=request
                )

        if start_review:
            request = (
                CaseWorkflowService
                .transition(
                    request=request,
                    target_status=(
                        RightsRequest
                        .Status
                        .UNDER_REVIEW
                    ),
                    actor=self.manager,
                )
            )

        return request

    def test_approve_creates_encrypted_resolution(self):
        request = self.create_request()

        plaintext = (
            "Resolución favorable."
        )

        resolution = (
            ResolutionService.approve(
                request=request,
                details=plaintext,
                actor=self.manager,
                legal_basis=(
                    "Base jurídica de prueba"
                ),
            )
        )

        request.refresh_from_db()
        resolution.refresh_from_db()

        self.assertEqual(
            resolution.resolution_type,
            RequestResolution
            .ResolutionType
            .APPROVED,
        )

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )

        self.assertNotIn(
            plaintext.encode("utf-8"),
            bytes(
                resolution
                .resolution_details_encrypted
            ),
        )

        self.assertEqual(
            ResolutionService
            .decrypt_details(resolution),
            plaintext,
        )

    def test_partial_approval_changes_status(self):
        request = self.create_request()

        resolution = (
            ResolutionService
            .partially_approve(
                request=request,
                details=(
                    "Aprobación parcial."
                ),
                actor=self.manager,
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            resolution.resolution_type,
            RequestResolution
            .ResolutionType
            .PARTIALLY_APPROVED,
        )

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .PARTIALLY_APPROVED,
        )

    def test_rejection_requires_matching_reason(self):
        request = self.create_request()

        with self.assertRaises(
            ResolutionReasonError
        ):
            ResolutionService.reject(
                request=request,
                details="Rechazo.",
                outcome_reason=(
                    self.archive_reason
                ),
                actor=self.manager,
            )

        self.assertFalse(
            RequestResolution.objects
            .filter(request=request)
            .exists()
        )

    def test_rejection_completes_deadline(self):
        request = self.create_request()

        ResolutionService.reject(
            request=request,
            details="Rechazo válido.",
            outcome_reason=(
                self.rejection_reason
            ),
            actor=self.manager,
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .REJECTED,
        )

        self.assertIsNone(
            request.current_due_at
        )

        deadline = (
            RequestDeadline.objects
            .get(request=request)
        )

        self.assertEqual(
            deadline.status,
            RequestDeadline
            .Status
            .COMPLETED,
        )

    def test_operator_cannot_resolve(self):
        request = self.create_request()

        with self.assertRaises(
            CasePermissionError
        ):
            ResolutionService.approve(
                request=request,
                details="No autorizado.",
                actor=self.operator,
            )

        self.assertFalse(
            RequestResolution.objects
            .filter(request=request)
            .exists()
        )

    def test_duplicate_resolution_is_rejected(self):
        request = self.create_request()

        ResolutionService.approve(
            request=request,
            details="Primera resolución.",
            actor=self.manager,
        )

        with self.assertRaises(
            ResolutionConflictError
        ):
            ResolutionService.approve(
                request=request,
                details="Segunda resolución.",
                actor=self.manager,
            )

        self.assertEqual(
            RequestResolution.objects
            .filter(request=request)
            .count(),
            1,
        )

    def test_approved_request_can_be_marked_responded(self):
        request = self.create_request()

        ResolutionService.approve(
            request=request,
            details="Aprobada.",
            actor=self.manager,
        )

        result = (
            ResolutionService
            .mark_responded(
                request=request,
                actor=self.manager,
            )
        )

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            RightsRequest
            .Status
            .RESPONDED,
        )

        self.assertIsNotNone(
            result.responded_at
        )

        self.assertIsNone(
            result.current_due_at
        )

        self.assertFalse(
            RequestDeadline.objects
            .filter(
                request=result,
                status__in=[
                    RequestDeadline
                    .Status
                    .ACTIVE,
                    RequestDeadline
                    .Status
                    .PAUSED,
                ],
            )
            .exists()
        )

    def test_responded_request_can_be_closed(self):
        request = self.create_request()

        ResolutionService.approve(
            request=request,
            details="Aprobada.",
            actor=self.manager,
        )

        request = (
            ResolutionService
            .mark_responded(
                request=request,
                actor=self.manager,
            )
        )

        result = ResolutionService.close(
            request=request,
            actor=self.manager,
        )

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            RightsRequest
            .Status
            .CLOSED,
        )

        self.assertIsNotNone(
            result.closed_at
        )

    def test_cancel_from_received(self):
        request = self.create_request(
            start_review=False,
        )

        ResolutionService.cancel(
            request=request,
            details="Cancelación.",
            outcome_reason=(
                self.cancel_reason
            ),
            actor=self.manager,
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .CANCELLED,
        )

    def test_archive_requires_expired_clarification(self):
        request = self.create_request()

        clarification = (
            CaseWorkflowService
            .request_clarification(
                request=request,
                message="Aclare.",
                actor=self.manager,
            )
        )

        request.refresh_from_db()

        with self.assertRaises(
            ResolutionStateError
        ):
            ResolutionService.archive(
                request=request,
                details="Archivo.",
                outcome_reason=(
                    self.archive_reason
                ),
                actor=self.manager,
            )

        RequestClarification.objects \
            .filter(
                pk=clarification.pk
            ) \
            .update(
                status=(
                    RequestClarification
                    .Status
                    .EXPIRED
                )
            )

        resolution = (
            ResolutionService.archive(
                request=request,
                details=(
                    "Archivo por falta "
                    "de subsanación."
                ),
                outcome_reason=(
                    self.archive_reason
                ),
                actor=self.manager,
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            resolution.resolution_type,
            RequestResolution
            .ResolutionType
            .ARCHIVED,
        )

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .ARCHIVED,
        )

    def test_close_is_blocked_by_open_clarification(self):
        request = self.create_request()

        ResolutionService.reject(
            request=request,
            details="Rechazo.",
            outcome_reason=(
                self.rejection_reason
            ),
            actor=self.manager,
        )

        RequestClarification.objects.create(
            request=request,
            requested_at=(
                request.received_at
            ),
            status=(
                RequestClarification
                .Status
                .REQUESTED
            ),
            request_message_encrypted=b"x",
            encryption_key_version=1,
            deadline_effect=(
                RequestClarification
                .DeadlineEffect
                .NO_CHANGE
            ),
            created_by=self.manager,
        )

        with self.assertRaises(
            ResolutionCloseBlockedError
        ):
            ResolutionService.close(
                request=request,
                actor=self.manager,
            )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .REJECTED,
        )

    def test_resolution_audit_does_not_store_details(self):
        request = self.create_request()

        plaintext = (
            "Detalle jurídico reservado."
        )

        ResolutionService.reject(
            request=request,
            details=plaintext,
            outcome_reason=(
                self.rejection_reason
            ),
            actor=self.manager,
        )

        audit = AuditLog.objects.get(
            action=(
                "REQUEST_RESOLUTION_CREATED"
            ),
            entity_pk=str(request.id),
        )

        serialized = str(
            audit.metadata
        )

        self.assertNotIn(
            plaintext,
            serialized,
        )

        self.assertEqual(
            audit.metadata[
                "resolution_type"
            ],
            "REJECTED",
        )

        self.assertEqual(
            audit.metadata[
                "outcome_reason_code"
            ],
            "TEST_REJECTION",
        )
