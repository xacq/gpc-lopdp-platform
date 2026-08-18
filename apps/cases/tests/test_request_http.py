import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.cases.models import RightsRequest
from apps.cases.services.cases import CaseWorkflowService
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService

ENCRYPTION_KEY = base64.b64encode(b"U" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"V" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
)
class RequestHttpTests(TestCase):
    def setUp(self):
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
            code="TEST_RIGHT",
            name="Derecho de prueba",
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
        self.other_operator = self.create_user_with_role(
            email="other-operator@example.com",
            role_code=Role.Code.OPERADOR,
        )
        self.auditor = self.create_user_with_role(
            email="auditor@example.com",
            role_code=Role.Code.AUDITOR,
        )

        self.request_one = CaseWorkflowService.create_request(
            data_subject=self.subject,
            right=self.right,
            request_details="Solicitud reservada uno",
        )
        self.request_two = CaseWorkflowService.create_request(
            data_subject=self.subject,
            right=self.right,
            request_details="Solicitud reservada dos",
        )
        self.request_one = CaseWorkflowService.assign(
            request=self.request_one,
            assignee=self.operator,
            actor=self.manager,
        )

    def create_user_with_role(self, *, email, role_code):
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

    def test_unauthenticated_list_redirects_to_login(self):
        response = self.client.get(reverse("cases:request_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_manager_sees_all_cases(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("cases:request_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.request_one.reference_number)
        self.assertContains(response, self.request_two.reference_number)

    def test_operator_only_sees_assigned_cases(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse("cases:request_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.request_one.reference_number)
        self.assertNotContains(response, self.request_two.reference_number)

    def test_operator_cannot_open_unassigned_case(self):
        self.client.force_login(self.operator)
        response = self.client.get(
            reverse(
                "cases:request_detail",
                kwargs={"request_id": self.request_two.id},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_auditor_detail_hides_sensitive_data(self):
        self.client.force_login(self.auditor)
        response = self.client.get(
            reverse(
                "cases:request_detail",
                kwargs={"request_id": self.request_one.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["sensitive_data"])
        self.assertNotContains(response, "Titular Prueba")
        self.assertNotContains(response, "1712345678")
        self.assertNotContains(response, "subject@example.com")

    def test_manager_detail_decrypts_through_service(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse(
                "cases:request_detail",
                kwargs={"request_id": self.request_one.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["sensitive_data"])
        self.assertContains(response, "Titular Prueba")
        self.assertContains(response, "Solicitud reservada uno")

    def test_operator_cannot_assign_case(self):
        self.client.force_login(self.operator)
        response = self.client.post(
            reverse(
                "cases:request_assign",
                kwargs={"request_id": self.request_one.id},
            ),
            {"assignee": self.other_operator.id},
        )
        self.assertEqual(response.status_code, 403)
        self.request_one.refresh_from_db()
        self.assertEqual(self.request_one.assigned_to_id, self.operator.id)

    def test_manager_can_assign_case(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse(
                "cases:request_assign",
                kwargs={"request_id": self.request_two.id},
            ),
            {"assignee": self.other_operator.id},
        )
        self.assertEqual(response.status_code, 302)
        self.request_two.refresh_from_db()
        self.assertEqual(
            self.request_two.assigned_to_id,
            self.other_operator.id,
        )

    def test_start_review_does_not_accept_get(self):
        self.client.force_login(self.operator)
        response = self.client.get(
            reverse(
                "cases:request_start_review",
                kwargs={"request_id": self.request_one.id},
            )
        )
        self.assertEqual(response.status_code, 405)
        self.request_one.refresh_from_db()
        self.assertEqual(self.request_one.status, RightsRequest.Status.RECEIVED)

    def test_assigned_operator_can_start_review(self):
        self.client.force_login(self.operator)
        response = self.client.post(
            reverse(
                "cases:request_start_review",
                kwargs={"request_id": self.request_one.id},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.request_one.refresh_from_db()
        self.assertEqual(
            self.request_one.status,
            RightsRequest.Status.UNDER_REVIEW,
        )
