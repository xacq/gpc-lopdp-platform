import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.cases.models import (
    CaseOutcomeReason,
    RequestDeadline,
    RequestResolution,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.cases.services.deadlines import (
    DeadlineService,
)
from apps.cases.services.resolutions import (
    ResolutionService,
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
    b"W" * 32
).decode("ascii")
LOOKUP_KEY = base64.b64encode(
    b"X" * 32
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
class ResolutionHttpTests(TestCase):
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
            timezone="America/Guayaquil",
        )

        self.right = RightCatalog.objects.create(
            code="TEST_RIGHT",
            name="Derecho de prueba",
            is_active=True,
        )

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

        self.subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Prueba",
            email="subject@example.com",
        )

        self.manager = self.create_user(
            "manager@example.com",
            Role.Code.RESPONSABLE,
        )
        self.operator = self.create_user(
            "operator@example.com",
            Role.Code.OPERADOR,
        )
        self.auditor = self.create_user(
            "auditor@example.com",
            Role.Code.AUDITOR,
        )

        self.rejection_reason = (
            CaseOutcomeReason.objects.create(
                reason_type=(
                    CaseOutcomeReason
                    .ReasonType
                    .REJECTION
                ),
                code="TEST_REJECTION",
                name="Causal de rechazo",
                is_active=True,
            )
        )
        self.cancel_reason = (
            CaseOutcomeReason.objects.create(
                reason_type=(
                    CaseOutcomeReason
                    .ReasonType
                    .CANCELLATION
                ),
                code="TEST_CANCEL",
                name="Causal de cancelación",
                is_active=True,
            )
        )
        self.inactive_reason = (
            CaseOutcomeReason.objects.create(
                reason_type=(
                    CaseOutcomeReason
                    .ReasonType
                    .REJECTION
                ),
                code="INACTIVE_REJECTION",
                name="Causal inactiva",
                is_active=False,
            )
        )

    def create_user(self, email, role_code):
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
        case = CaseWorkflowService.create_request(
            data_subject=self.subject,
            right=self.right,
            request_details="Solicitud de prueba",
        )

        if initialize_deadline:
            DeadlineService.initialize_initial(
                request=case
            )

        if start_review:
            case = CaseWorkflowService.transition(
                request=case,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=self.manager,
            )

        return case

    def test_unauthenticated_resolution_redirects_to_login(self):
        case = self.create_request()
        response = self.client.get(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "/accounts/login/",
            response["Location"],
        )

    def test_resolution_requires_recent_sensitive_reauthentication(self):
        case = self.create_request()
        force_mfa_login(
            self.client,
            self.manager,
            sensitive=False,
        )
        response = self.client.get(
            reverse(
                "cases:request_resolution",
                kwargs={"request_id": case.id},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:reauth"),
            response["Location"],
        )

    def test_close_requires_recent_sensitive_reauthentication(self):
        case = self.create_request()
        force_mfa_login(
            self.client,
            self.manager,
            sensitive=False,
        )
        response = self.client.post(
            reverse(
                "cases:request_close",
                kwargs={"request_id": case.id},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:reauth"),
            response["Location"],
        )

    def test_operator_cannot_resolve(self):
        case = self.create_request()
        case = CaseWorkflowService.assign(
            request=case,
            assignee=self.operator,
            actor=self.manager,
        )
        force_mfa_login(self.client, self.operator)
        response = self.client.post(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            ),
            {
                "resolution_type": "APPROVED",
                "details": "No autorizado.",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            RequestResolution.objects
            .filter(request=case)
            .exists()
        )

    def test_auditor_cannot_resolve(self):
        case = self.create_request()
        force_mfa_login(self.client, self.auditor)
        response = self.client.get(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 403)

    def test_resolution_get_does_not_mutate(self):
        case = self.create_request()
        force_mfa_login(self.client, self.manager)
        response = self.client.get(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            RequestResolution.objects
            .filter(request=case)
            .exists()
        )
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )

    def test_resolution_form_exposes_only_active_reasons(self):
        case = self.create_request()
        force_mfa_login(self.client, self.manager)
        response = self.client.get(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        queryset = (
            response.context["form"]
            .fields["outcome_reason"]
            .queryset
        )
        self.assertIn(
            self.rejection_reason,
            queryset,
        )
        self.assertNotIn(
            self.inactive_reason,
            queryset,
        )
        self.assertContains(
            response,
            f'data-reason-type="{self.rejection_reason.reason_type}"',
        )

    def test_manager_can_approve(self):
        case = self.create_request()
        details = "Resolución favorable reservada."
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            ),
            {
                "resolution_type": "APPROVED",
                "details": details,
                "legal_basis": "Base de prueba",
            },
        )
        self.assertEqual(response.status_code, 302)
        resolution = RequestResolution.objects.get(
            request=case
        )
        self.assertEqual(
            resolution.resolution_type,
            RequestResolution
            .ResolutionType
            .APPROVED,
        )
        self.assertNotIn(
            details.encode("utf-8"),
            bytes(
                resolution
                .resolution_details_encrypted
            ),
        )
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )

    def test_partial_approval_changes_status(self):
        case = self.create_request()
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            ),
            {
                "resolution_type": (
                    "PARTIALLY_APPROVED"
                ),
                "details": "Aprobación parcial.",
            },
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest
            .Status
            .PARTIALLY_APPROVED,
        )

    def test_rejection_requires_matching_reason(self):
        case = self.create_request()
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            ),
            {
                "resolution_type": "REJECTED",
                "details": "Rechazo.",
                "outcome_reason": (
                    self.cancel_reason.id
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            RequestResolution.objects
            .filter(request=case)
            .exists()
        )
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )

    def test_rejection_closes_active_deadline(self):
        case = self.create_request()
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            ),
            {
                "resolution_type": "REJECTED",
                "details": "Rechazo válido.",
                "outcome_reason": (
                    self.rejection_reason.id
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.REJECTED,
        )
        self.assertIsNone(case.current_due_at)
        deadline = RequestDeadline.objects.get(
            request=case
        )
        self.assertEqual(
            deadline.status,
            RequestDeadline.Status.COMPLETED,
        )

    def test_cancel_from_received(self):
        case = self.create_request(
            start_review=False,
        )
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            ),
            {
                "resolution_type": "CANCELLED",
                "details": "Cancelación válida.",
                "outcome_reason": (
                    self.cancel_reason.id
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.CANCELLED,
        )

    def test_duplicate_resolution_is_rejected(self):
        case = self.create_request()
        ResolutionService.approve(
            request=case,
            details="Primera resolución.",
            actor=self.manager,
        )
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_resolution",
                kwargs={
                    "request_id": case.id,
                },
            ),
            {
                "resolution_type": "APPROVED",
                "details": "Segunda resolución.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            RequestResolution.objects
            .filter(request=case)
            .count(),
            1,
        )

    def test_mark_responded_rejects_get(self):
        case = self.create_request()
        ResolutionService.approve(
            request=case,
            details="Aprobada.",
            actor=self.manager,
        )
        force_mfa_login(self.client, self.manager)
        response = self.client.get(
            reverse(
                "cases:request_mark_responded",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 405)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )

    def test_manager_can_mark_approved_request_responded(self):
        case = self.create_request()
        ResolutionService.approve(
            request=case,
            details="Aprobada.",
            actor=self.manager,
        )
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_mark_responded",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.RESPONDED,
        )
        self.assertIsNotNone(case.responded_at)
        self.assertIsNone(case.current_due_at)

    def test_mark_responded_without_resolution_is_bad_request(self):
        case = self.create_request()
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_mark_responded",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 400)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )

    def test_operator_cannot_mark_responded(self):
        case = self.create_request()
        ResolutionService.approve(
            request=case,
            details="Aprobada.",
            actor=self.manager,
        )
        case = CaseWorkflowService.assign(
            request=case,
            assignee=self.operator,
            actor=self.manager,
        )
        force_mfa_login(self.client, self.operator)
        response = self.client.post(
            reverse(
                "cases:request_mark_responded",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 403)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )

    def test_close_rejects_get(self):
        case = self.create_request()
        ResolutionService.approve(
            request=case,
            details="Aprobada.",
            actor=self.manager,
        )
        case = ResolutionService.mark_responded(
            request=case,
            actor=self.manager,
        )
        force_mfa_login(self.client, self.manager)
        response = self.client.get(
            reverse(
                "cases:request_close",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 405)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.RESPONDED,
        )

    def test_manager_can_close_responded_request(self):
        case = self.create_request()
        ResolutionService.approve(
            request=case,
            details="Aprobada.",
            actor=self.manager,
        )
        case = ResolutionService.mark_responded(
            request=case,
            actor=self.manager,
        )
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_close",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.CLOSED,
        )
        self.assertIsNotNone(case.closed_at)

    def test_manager_can_close_rejected_request(self):
        case = self.create_request()
        ResolutionService.reject(
            request=case,
            details="Rechazo.",
            outcome_reason=self.rejection_reason,
            actor=self.manager,
        )
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_close",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.CLOSED,
        )

    def test_close_without_resolution_is_bad_request(self):
        case = self.create_request()
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse(
                "cases:request_close",
                kwargs={
                    "request_id": case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 400)
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
