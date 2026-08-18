import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.cases.models import (
    RequestClarification,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.cases.services.deadlines import (
    DeadlineService,
)
from apps.legal_content.models import (
    RightCatalog,
    RightRule,
)
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService

ENCRYPTION_KEY = base64.b64encode(
    b"Y" * 32
).decode("ascii")
LOOKUP_KEY = base64.b64encode(
    b"Z" * 32
).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
)
class ClarificationHttpTests(TestCase):
    def setUp(self):
        SystemSetting.objects.create(
            legal_name=(
                "VINOS Y ESPIRITUOSOS "
                "VINESA S.A."
            ),
            trade_name="VINESA",
            ruc="1792049598001",
            domain="privacidad.vinesa.test",
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

        self.rule = RightRule.objects.create(
            right=self.right,
            response_days=5,
            day_count_type=(
                RightRule.DayCountType.BUSINESS
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
            phone="+593991234567",
        )

        self.manager = self.create_user_with_role(
            email="manager@example.com",
            role_code=Role.Code.RESPONSABLE,
        )
        self.operator = self.create_user_with_role(
            email="operator@example.com",
            role_code=Role.Code.OPERADOR,
        )
        self.other_operator = (
            self.create_user_with_role(
                email=(
                    "other-operator@example.com"
                ),
                role_code=Role.Code.OPERADOR,
            )
        )
        self.auditor = self.create_user_with_role(
            email="auditor@example.com",
            role_code=Role.Code.AUDITOR,
        )

        self.case = self.create_review_case(
            assignee=self.operator,
        )
        self.unassigned_case = (
            CaseWorkflowService.create_request(
                data_subject=self.subject,
                right=self.right,
                request_details=(
                    "Expediente no asignado"
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

    def create_review_case(
        self,
        *,
        assignee=None,
    ):
        case = CaseWorkflowService.create_request(
            data_subject=self.subject,
            right=self.right,
            request_details=(
                "Solicitud de prueba"
            ),
        )

        DeadlineService.initialize_initial(
            request=case
        )

        if assignee is not None:
            case = CaseWorkflowService.assign(
                request=case,
                assignee=assignee,
                actor=self.manager,
            )

        actor = (
            assignee
            if assignee is not None
            else self.manager
        )

        return CaseWorkflowService.transition(
            request=case,
            target_status=(
                RightsRequest
                .Status
                .UNDER_REVIEW
            ),
            actor=actor,
        )

    def create_clarification(
        self,
        *,
        case=None,
        actor=None,
    ):
        return (
            CaseWorkflowService
            .request_clarification(
                request=case or self.case,
                message="Complete la información.",
                actor=actor or self.operator,
            )
        )

    def test_unauthenticated_request_redirects_to_login(self):
        response = self.client.get(
            reverse(
                "cases:request_clarification_create",
                kwargs={
                    "request_id": self.case.id,
                },
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "/accounts/login/",
            response["Location"],
        )

    def test_request_get_does_not_mutate_case(self):
        self.client.force_login(self.operator)

        response = self.client.get(
            reverse(
                "cases:request_clarification_create",
                kwargs={
                    "request_id": self.case.id,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
        self.assertEqual(
            RequestClarification.objects.filter(
                request=self.case
            ).count(),
            0,
        )

    def test_manager_can_request_clarification(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "cases:request_clarification_create",
                kwargs={
                    "request_id": self.case.id,
                },
            ),
            {
                "message": "Aclare los antecedentes.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest
            .Status
            .AWAITING_INFORMATION,
        )
        self.assertEqual(
            RequestClarification.objects.filter(
                request=self.case,
                status=(
                    RequestClarification
                    .Status
                    .REQUESTED
                ),
            ).count(),
            1,
        )

    def test_assigned_operator_can_request_clarification(self):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse(
                "cases:request_clarification_create",
                kwargs={
                    "request_id": self.case.id,
                },
            ),
            {
                "message": "Complete el documento.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest
            .Status
            .AWAITING_INFORMATION,
        )

    def test_auditor_cannot_request_clarification(self):
        self.client.force_login(self.auditor)

        response = self.client.post(
            reverse(
                "cases:request_clarification_create",
                kwargs={
                    "request_id": self.case.id,
                },
            ),
            {
                "message": "Intento no autorizado.",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
        self.assertFalse(
            RequestClarification.objects.filter(
                request=self.case
            ).exists()
        )

    def test_unassigned_operator_cannot_access_case(self):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse(
                "cases:request_clarification_create",
                kwargs={
                    "request_id": (
                        self.unassigned_case.id
                    ),
                },
            ),
            {
                "message": "No debe permitirse.",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.unassigned_case.refresh_from_db()
        self.assertEqual(
            self.unassigned_case.status,
            RightsRequest.Status.RECEIVED,
        )

    def test_empty_message_does_not_mutate_case(self):
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse(
                "cases:request_clarification_create",
                kwargs={
                    "request_id": self.case.id,
                },
            ),
            {
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
        self.assertFalse(
            RequestClarification.objects.filter(
                request=self.case
            ).exists()
        )

    def test_receive_get_does_not_mutate_clarification(self):
        clarification = self.create_clarification()
        self.client.force_login(self.operator)

        response = self.client.get(
            reverse(
                "cases:request_clarification_receive",
                kwargs={
                    "request_id": self.case.id,
                    "clarification_id": (
                        clarification.id
                    ),
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        clarification.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(
            clarification.status,
            RequestClarification.Status.REQUESTED,
        )
        self.assertEqual(
            self.case.status,
            RightsRequest
            .Status
            .AWAITING_INFORMATION,
        )

    def test_assigned_operator_can_receive_clarification(self):
        clarification = self.create_clarification()
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse(
                "cases:request_clarification_receive",
                kwargs={
                    "request_id": self.case.id,
                    "clarification_id": (
                        clarification.id
                    ),
                },
            ),
            {
                "response_message": (
                    "Información completada."
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        clarification.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(
            clarification.status,
            RequestClarification.Status.RECEIVED,
        )
        self.assertIsNotNone(
            clarification.received_at
        )
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )

    def test_wrong_case_clarification_binding_returns_404(self):
        other_case = self.create_review_case()
        other_clarification = (
            self.create_clarification(
                case=other_case,
                actor=self.manager,
            )
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "cases:request_clarification_receive",
                kwargs={
                    "request_id": self.case.id,
                    "clarification_id": (
                        other_clarification.id
                    ),
                },
            ),
            {
                "response_message": "Respuesta.",
            },
        )

        self.assertEqual(response.status_code, 404)
        other_clarification.refresh_from_db()
        self.assertEqual(
            other_clarification.status,
            RequestClarification.Status.REQUESTED,
        )

    def test_duplicate_receive_is_rejected_without_second_mutation(self):
        clarification = self.create_clarification()
        self.client.force_login(self.operator)
        url = reverse(
            "cases:request_clarification_receive",
            kwargs={
                "request_id": self.case.id,
                "clarification_id": clarification.id,
            },
        )

        first = self.client.post(
            url,
            {
                "response_message": "Primera respuesta.",
            },
        )
        second = self.client.post(
            url,
            {
                "response_message": "Segunda respuesta.",
            },
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 200)
        clarification.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(
            clarification.status,
            RequestClarification.Status.RECEIVED,
        )
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
