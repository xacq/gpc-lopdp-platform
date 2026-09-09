from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.cases.models import RightsRequest
from apps.cases.services.dashboard import CaseDashboardService
from apps.legal_content.models import RightCatalog
from apps.subjects.models import DataSubject


class DashboardSummaryTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.right = RightCatalog.objects.create(
            code="ACCESS",
            name="Acceso",
            is_active=True,
        )
        self.subject = DataSubject.objects.create(
            subject_type=DataSubject.SubjectType.CUSTOMER,
            document_type=DataSubject.DocumentType.CEDULA,
            document_number_encrypted=b"encrypted-document",
            document_number_lookup_hash="a" * 64,
            full_name_encrypted=b"encrypted-full-name",
            email_encrypted=b"encrypted-email",
            email_lookup_hash="b" * 64,
        )
        self.manager = self._user("manager@example.test", Role.Code.RESPONSABLE)
        self.operator = self._user("operator@example.test", Role.Code.OPERADOR)
        self.auditor = self._user("auditor@example.test", Role.Code.AUDITOR)
        self.outsider = get_user_model().objects.create_user(
            email="outsider@example.test",
            password="StrongDashboardPassword!593",
            full_name="Usuario sin rol",
            is_active=True,
        )

        self.overdue = self._request(
            reference="VS-DASH-001",
            status=RightsRequest.Status.UNDER_REVIEW,
            received_at=self.now - timedelta(hours=1),
            due_at=self.now - timedelta(days=1),
            assigned_to=self.operator,
        )
        self.due_soon = self._request(
            reference="VS-DASH-002",
            status=RightsRequest.Status.RECEIVED,
            received_at=self.now - timedelta(hours=2),
            due_at=self.now + timedelta(days=2),
        )
        self.later = self._request(
            reference="VS-DASH-003",
            status=RightsRequest.Status.EXTENDED,
            received_at=self.now - timedelta(hours=3),
            due_at=self.now + timedelta(days=20),
        )
        self.closed = self._request(
            reference="VS-DASH-004",
            status=RightsRequest.Status.CLOSED,
            received_at=self.now - timedelta(hours=4),
        )

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongDashboardPassword!593",
            full_name=f"Usuario {role_code}",
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(
            user=user,
            role=role,
            is_primary=True,
        )
        return user

    def _request(
        self,
        *,
        reference,
        status,
        received_at,
        due_at=None,
        assigned_to=None,
    ):
        return RightsRequest.objects.create(
            data_subject=self.subject,
            right=self.right,
            reference_number=reference,
            request_details_encrypted=b"encrypted-request",
            subject_snapshot_encrypted=b"encrypted-snapshot",
            status=status,
            received_at=received_at,
            current_due_at=due_at,
            assigned_to=assigned_to,
        )

    def test_unauthenticated_request_redirects_to_login(self):
        response = self.client.get(reverse("core:dashboard_summary"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_dashboard_page_renders_operational_metrics(self):
        force_mfa_login(self.client, self.manager)

        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Panel de control")
        self.assertContains(response, "Total expedientes")
        self.assertContains(response, "VS-DASH-001")
        self.assertIn("no-cache", response["Cache-Control"])

    def test_user_without_panel_role_is_forbidden(self):
        force_mfa_login(self.client, self.outsider)

        response = self.client.get(reverse("core:dashboard_summary"))

        self.assertEqual(response.status_code, 403)

        page_response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(page_response.status_code, 403)

    def test_manager_receives_global_non_pii_metrics(self):
        force_mfa_login(self.client, self.manager)

        response = self.client.get(reverse("core:dashboard_summary"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-cache", response["Cache-Control"])
        payload = response.json()
        self.assertEqual(payload["scope"], "ALL")
        self.assertEqual(
            payload["metrics"],
            {
                "total": 4,
                "active": 3,
                "received": 1,
                "in_review": 2,
                "finalized": 1,
                "unassigned": 2,
                "due_soon": 1,
                "overdue": 1,
            },
        )
        self.assertEqual(
            payload["latest_requests"][0]["reference_number"],
            self.overdue.reference_number,
        )
        serialized = response.content.decode("utf-8")
        for forbidden in (
            "data_subject",
            "full_name",
            "document_number",
            "email",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_operator_metrics_are_limited_to_assigned_requests(self):
        force_mfa_login(self.client, self.operator)

        response = self.client.get(reverse("core:dashboard_summary"))

        payload = response.json()
        self.assertEqual(payload["scope"], "ASSIGNED")
        self.assertEqual(payload["metrics"]["total"], 1)
        self.assertEqual(payload["metrics"]["overdue"], 1)
        self.assertEqual(len(payload["latest_requests"]), 1)
        self.assertEqual(
            payload["latest_requests"][0]["reference_number"],
            self.overdue.reference_number,
        )

    def test_auditor_can_read_summary_without_subject_data(self):
        force_mfa_login(self.client, self.auditor)

        response = self.client.get(reverse("core:dashboard_summary"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "ALL")
        self.assertNotContains(response, "Usuario sin rol")

    def test_endpoint_is_get_only(self):
        force_mfa_login(self.client, self.manager)

        response = self.client.post(reverse("core:dashboard_summary"))

        self.assertEqual(response.status_code, 405)

    def test_service_rejects_unbounded_latest_limit(self):
        with self.assertRaises(ValueError):
            CaseDashboardService.snapshot(
                user=self.manager,
                generated_at=self.now,
                latest_limit=51,
            )
