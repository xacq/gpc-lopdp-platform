import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.cases.models import (
    RequestDeadline,
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
    b"1" * 32
).decode("ascii")
LOOKUP_KEY = base64.b64encode(
    b"2" * 32
).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
)
class ExtensionHttpTests(TestCase):
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
        self.auditor = self.create_user_with_role(
            email="auditor@example.com",
            role_code=Role.Code.AUDITOR,
        )

        self.case = self.create_review_case()

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
        initialize_deadline=True,
    ):
        case = CaseWorkflowService.create_request(
            data_subject=self.subject,
            right=self.right,
            request_details=(
                "Solicitud de prueba"
            ),
        )

        if initialize_deadline:
            DeadlineService.initialize_initial(
                request=case
            )

        return CaseWorkflowService.transition(
            request=case,
            target_status=(
                RightsRequest
                .Status
                .UNDER_REVIEW
            ),
            actor=self.manager,
        )

    def extension_url(self, case=None):
        case = case or self.case
        return reverse(
            "cases:request_extension",
            kwargs={
                "request_id": case.id,
            },
        )

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(
            self.extension_url()
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertIn(
            "/accounts/login/",
            response["Location"],
        )

    def test_get_does_not_mutate_case(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            self.extension_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
        self.assertFalse(
            self.case.extension_applied
        )
        self.assertEqual(
            RequestDeadline.objects.filter(
                request=self.case,
                deadline_type=(
                    RequestDeadline
                    .DeadlineType
                    .EXTENSION
                ),
            ).count(),
            0,
        )

    def test_manager_can_extend_under_review_case(self):
        self.client.force_login(self.manager)
        initial_due_at = self.case.current_due_at

        response = self.client.post(
            self.extension_url(),
            {
                "reason": (
                    "Complejidad técnica del caso."
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.EXTENDED,
        )
        self.assertTrue(
            self.case.extension_applied
        )
        self.assertNotEqual(
            self.case.current_due_at,
            initial_due_at,
        )

        extension = RequestDeadline.objects.get(
            request=self.case,
            deadline_type=(
                RequestDeadline
                .DeadlineType
                .EXTENSION
            ),
        )
        self.assertEqual(
            extension.status,
            RequestDeadline.Status.ACTIVE,
        )
        self.assertEqual(
            self.case.current_due_at,
            extension.due_at,
        )

    def test_extension_while_awaiting_information_keeps_state(self):
        clarification = (
            CaseWorkflowService
            .request_clarification(
                request=self.case,
                message="Complete la información.",
                actor=self.manager,
            )
        )
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest
            .Status
            .AWAITING_INFORMATION,
        )

        self.client.force_login(self.manager)
        response = self.client.post(
            self.extension_url(),
            {
                "reason": "Extensión durante aclaración.",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest
            .Status
            .AWAITING_INFORMATION,
        )
        self.assertTrue(
            self.case.extension_applied
        )

        CaseWorkflowService.receive_clarification(
            clarification=clarification,
            response_message="Información recibida.",
            actor=self.manager,
        )
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.EXTENDED,
        )

    def test_operator_cannot_access_extension(self):
        self.client.force_login(self.operator)

        response = self.client.post(
            self.extension_url(),
            {
                "reason": "No autorizado.",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )
        self.case.refresh_from_db()
        self.assertFalse(
            self.case.extension_applied
        )

    def test_auditor_cannot_access_extension(self):
        self.client.force_login(self.auditor)

        response = self.client.get(
            self.extension_url()
        )

        self.assertEqual(
            response.status_code,
            403,
        )
        self.case.refresh_from_db()
        self.assertFalse(
            self.case.extension_applied
        )

    def test_empty_reason_does_not_mutate_case(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            self.extension_url(),
            {
                "reason": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
        self.assertFalse(
            self.case.extension_applied
        )

    def test_extension_not_allowed_does_not_mutate_case(self):
        self.rule.extension_allowed = False
        self.rule.extension_days = 0
        self.rule.save(
            update_fields=[
                "extension_allowed",
                "extension_days",
            ]
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            self.extension_url(),
            {
                "reason": "Intento no permitido.",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
        self.assertFalse(
            self.case.extension_applied
        )
        self.assertEqual(
            RequestDeadline.objects.filter(
                request=self.case,
                deadline_type=(
                    RequestDeadline
                    .DeadlineType
                    .EXTENSION
                ),
            ).count(),
            0,
        )

    def test_second_extension_is_rejected_without_duplicate(self):
        self.client.force_login(self.manager)
        url = self.extension_url()

        first = self.client.post(
            url,
            {
                "reason": "Primera extensión.",
            },
        )
        second = self.client.post(
            url,
            {
                "reason": "Segunda extensión.",
            },
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(
            self.case.status,
            RightsRequest.Status.EXTENDED,
        )
        self.assertTrue(
            self.case.extension_applied
        )
        self.assertEqual(
            RequestDeadline.objects.filter(
                request=self.case,
                deadline_type=(
                    RequestDeadline
                    .DeadlineType
                    .EXTENSION
                ),
            ).count(),
            1,
        )

    def test_missing_active_deadline_does_not_mutate_case(self):
        case = self.create_review_case(
            initialize_deadline=False,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            self.extension_url(case),
            {
                "reason": "No existe plazo activo.",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        case.refresh_from_db()
        self.assertEqual(
            case.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
        self.assertFalse(
            case.extension_applied
        )
