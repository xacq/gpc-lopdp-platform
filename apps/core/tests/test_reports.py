from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.cases.models import RightsRequest
from apps.legal_content.models import RightCatalog
from apps.subjects.models import DataSubject


class ReportBackendTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.access_right = RightCatalog.objects.create(
            code="ACCESS",
            name="Acceso",
            is_active=True,
        )
        self.deletion_right = RightCatalog.objects.create(
            code="DELETION",
            name="Eliminación",
            is_active=True,
        )
        self.subject = DataSubject.objects.create(
            subject_type=DataSubject.SubjectType.CUSTOMER,
            document_type=DataSubject.DocumentType.CEDULA,
            document_number_encrypted=b"encrypted-document",
            document_number_lookup_hash="c" * 64,
            full_name_encrypted=b"encrypted-name",
            email_encrypted=b"encrypted-email",
            email_lookup_hash="d" * 64,
        )
        self.manager = self._user("report-manager@example.test", Role.Code.DPD)
        self.operator = self._user(
            "report-operator@example.test",
            Role.Code.OPERADOR,
        )
        self.outsider = get_user_model().objects.create_user(
            email="report-outsider@example.test",
            password="StrongReportPassword!593",
            full_name="Titular secreto no publicable",
            is_active=True,
        )

        self._request(
            reference="VS-REPORT-001",
            right=self.access_right,
            status=RightsRequest.Status.RESPONDED,
            received_at=self.now - timedelta(days=10),
            responded_at=self.now - timedelta(days=8),
            assigned_to=self.operator,
        )
        self._request(
            reference="VS-REPORT-002",
            right=self.access_right,
            status=RightsRequest.Status.UNDER_REVIEW,
            received_at=self.now - timedelta(days=5),
            assigned_to=self.operator,
        )
        self._request(
            reference="VS-REPORT-003",
            right=self.deletion_right,
            status=RightsRequest.Status.RECEIVED,
            received_at=self.now - timedelta(days=2),
        )
        self._request(
            reference="VS-REPORT-004",
            right=self.deletion_right,
            status=RightsRequest.Status.CLOSED,
            received_at=self.now - timedelta(days=20),
            closed_at=self.now - timedelta(days=16),
        )

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongReportPassword!593",
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
        right,
        status,
        received_at,
        responded_at=None,
        closed_at=None,
        assigned_to=None,
    ):
        return RightsRequest.objects.create(
            data_subject=self.subject,
            right=right,
            reference_number=reference,
            request_details_encrypted=b"encrypted-request",
            subject_snapshot_encrypted=b"encrypted-snapshot",
            status=status,
            received_at=received_at,
            responded_at=responded_at,
            closed_at=closed_at,
            assigned_to=assigned_to,
        )

    def test_manager_receives_aggregated_report(self):
        force_mfa_login(self.client, self.manager)

        response = self.client.get(reverse("core:report_summary"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-cache", response["Cache-Control"])
        payload = response.json()
        self.assertEqual(
            payload["metrics"],
            {
                "total": 4,
                "finalized": 2,
                "in_process": 1,
                "pending": 1,
                "average_attention_days": 3.0,
            },
        )
        rights = {row["code"]: row for row in payload["by_right"]}
        self.assertEqual(rights["ACCESS"]["total"], 2)
        self.assertEqual(rights["ACCESS"]["completion_percentage"], 50.0)
        self.assertEqual(rights["DELETION"]["pending"], 1)

    def test_report_page_renders_aggregated_metrics_and_filters(self):
        force_mfa_login(self.client, self.manager)

        response = self.client.get(reverse("core:reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reportes")
        self.assertContains(response, "Resumen por derecho")
        self.assertContains(response, "Acceso")
        self.assertNotContains(response, "VS-REPORT-001")
        self.assertIn("no-cache", response["Cache-Control"])

    def test_filters_are_combined_and_normalized(self):
        force_mfa_login(self.client, self.manager)
        date_from = (self.now - timedelta(days=6)).date().isoformat()
        date_to = self.now.date().isoformat()

        response = self.client.get(
            reverse("core:report_summary"),
            {
                "date_from": date_from,
                "date_to": date_to,
                "right_code": " access ",
                "status": RightsRequest.Status.UNDER_REVIEW,
                "assigned_to": str(self.operator.id),
            },
        )

        payload = response.json()
        self.assertEqual(payload["metrics"]["total"], 1)
        self.assertEqual(payload["filters"]["right_code"], "ACCESS")
        self.assertEqual(
            payload["filters"]["assigned_to"],
            str(self.operator.id),
        )

    def test_operator_report_is_limited_to_assigned_cases(self):
        force_mfa_login(self.client, self.operator)

        response = self.client.get(reverse("core:report_summary"))

        self.assertEqual(response.json()["metrics"]["total"], 2)

    def test_invalid_date_ranges_return_safe_validation_errors(self):
        force_mfa_login(self.client, self.manager)

        response = self.client.get(
            reverse("core:report_summary"),
            {"date_from": self.now.date().isoformat()},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("__all__", response.json()["errors"])

    def test_csv_contains_only_aggregated_data(self):
        force_mfa_login(self.client, self.manager)

        response = self.client.get(reverse("core:report_export_csv"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("Código del derecho", content)
        self.assertIn("ACCESS,Acceso,2,1,1,0,50.0", content)
        self.assertNotIn("VS-REPORT", content)
        self.assertNotIn("report-operator@example.test", content)
        self.assertNotIn("Titular secreto", content)

    def test_unauthenticated_and_unauthorized_access_is_rejected(self):
        url = reverse("core:report_summary")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        force_mfa_login(self.client, self.outsider)
        response = self.client.get(url, {"date_from": "invalid"})
        self.assertEqual(response.status_code, 403)
