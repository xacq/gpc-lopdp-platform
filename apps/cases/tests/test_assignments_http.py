import base64
import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.cases.services.cases import CaseWorkflowService
from apps.legal_content.models import RightCatalog
from apps.subjects.models import DataSubject


ENCRYPTION_KEY = base64.b64encode(b"A" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    ASSIGNMENT_CAPACITY_PER_USER=25,
)
class AssignmentHttpTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.right = RightCatalog.objects.create(
            code="ASSIGN_ACCESS",
            name="Acceso",
            is_active=True,
        )
        self.subject = DataSubject.objects.create(
            subject_type=DataSubject.SubjectType.CUSTOMER,
            document_type=DataSubject.DocumentType.CEDULA,
            document_number_encrypted=b"secret-document",
            document_number_lookup_hash="d" * 64,
            full_name_encrypted=b"secret-name",
            email_encrypted=b"secret-email",
            email_lookup_hash="e" * 64,
        )
        self.manager = self._user("manager-assign@example.test", Role.Code.ADMIN)
        self.operator = self._user(
            "operator-assign@example.test", Role.Code.OPERADOR
        )
        self.other_operator = self._user(
            "other-assign@example.test", Role.Code.OPERADOR
        )
        self.auditor = self._user(
            "auditor-assign@example.test", Role.Code.AUDITOR
        )
        self.first = self._request(
            "VS-ASG-001",
            due_at=self.now + timedelta(hours=2),
        )
        self.second = self._request(
            "VS-ASG-002",
            due_at=self.now + timedelta(days=2),
        )

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongAssignmentPassword!593",
            full_name=f"Usuario {role_code} {email[:3]}",
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(user=user, role=role, is_primary=True)
        return user

    def _request(self, reference, *, due_at=None, assigned_to=None):
        return RightsRequest.objects.create(
            data_subject=self.subject,
            right=self.right,
            reference_number=reference,
            request_details_encrypted=b"encrypted-request",
            subject_snapshot_encrypted=b"encrypted-snapshot",
            status=RightsRequest.Status.RECEIVED,
            received_at=self.now,
            current_due_at=due_at,
            assigned_to=assigned_to,
        )

    def _post_assignment(self, request_ids, assignee_id):
        return self.client.post(
            reverse("assignments:apply"),
            data=json.dumps(
                {
                    "request_ids": [str(item) for item in request_ids],
                    "assignee_id": str(assignee_id),
                }
            ),
            content_type="application/json",
        )

    def test_unauthenticated_user_is_redirected(self):
        response = self.client.get(reverse("assignments:summary"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_operator_and_auditor_cannot_manage_assignments(self):
        for user in (self.operator, self.auditor):
            force_mfa_login(self.client, user)
            self.assertEqual(
                self.client.get(reverse("assignments:summary")).status_code,
                403,
            )
            self.client.logout()

    def test_summary_returns_metrics_and_operational_workload(self):
        self.first.assigned_to = self.operator
        self.first.save(update_fields=["assigned_to"])
        force_mfa_login(self.client, self.manager)

        response = self.client.get(reverse("assignments:summary"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-cache", response["Cache-Control"])
        payload = response.json()
        self.assertEqual(payload["metrics"]["active"], 2)
        self.assertEqual(payload["metrics"]["assigned"], 1)
        self.assertEqual(payload["metrics"]["unassigned"], 1)
        operator = next(
            item
            for item in payload["workload"]
            if item["user_id"] == str(self.operator.id)
        )
        self.assertEqual(operator["active_assignments"], 1)
        self.assertEqual(operator["capacity"], 25)

    def test_assignment_page_renders_metrics_and_safe_case_data(self):
        self.first.assigned_to = self.operator
        self.first.save(update_fields=["assigned_to"])
        force_mfa_login(self.client, self.manager)

        response = self.client.get(reverse("assignments:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asignaciones")
        self.assertContains(response, "VS-ASG-001")
        self.assertContains(response, self.operator.full_name)
        self.assertContains(response, "Asignar selección")
        self.assertContains(response, 'name="due_from"')
        self.assertContains(response, 'name="assigned_to"')
        self.assertNotContains(response, "secret-name")
        self.assertIn("no-cache", response["Cache-Control"])

    def test_list_filters_without_exposing_subject_data(self):
        self.first.assigned_to = self.operator
        self.first.save(update_fields=["assigned_to"])
        force_mfa_login(self.client, self.manager)

        response = self.client.get(
            reverse("assignments:request_list"),
            {"assignment_state": "ASSIGNED", "search": "ASG-001"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["results"][0]["id"], str(self.first.id))
        serialized = response.content.decode("utf-8")
        for forbidden in ("data_subject", "full_name_encrypted", "email_encrypted"):
            self.assertNotIn(forbidden, serialized)

    def test_bulk_assignment_is_audited_with_one_correlation_id(self):
        force_mfa_login(self.client, self.manager)

        response = self._post_assignment(
            [self.first.id, self.second.id], self.operator.id
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assigned"], 2)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.assigned_to_id, self.operator.id)
        self.assertEqual(self.second.assigned_to_id, self.operator.id)
        logs = AuditLog.objects.filter(
            action="RIGHTS_REQUEST_ASSIGNED",
            entity_pk__in=(str(self.first.id), str(self.second.id)),
        )
        self.assertEqual(logs.count(), 2)
        self.assertEqual(
            {str(item.correlation_id) for item in logs},
            {payload["correlation_id"]},
        )

    def test_missing_case_makes_bulk_operation_atomic(self):
        force_mfa_login(self.client, self.manager)

        response = self._post_assignment(
            [self.first.id, uuid.uuid4()], self.operator.id
        )

        self.assertEqual(response.status_code, 400)
        self.first.refresh_from_db()
        self.assertIsNone(self.first.assigned_to_id)
        self.assertFalse(
            AuditLog.objects.filter(
                action="RIGHTS_REQUEST_ASSIGNED",
                entity_pk=str(self.first.id),
            ).exists()
        )

    def test_reassignment_is_visible_in_history(self):
        CaseWorkflowService.assign(
            request=self.first,
            assignee=self.operator,
            actor=self.manager,
        )
        CaseWorkflowService.assign(
            request=self.first,
            assignee=self.other_operator,
            actor=self.manager,
        )
        force_mfa_login(self.client, self.manager)

        response = self.client.get(
            reverse("assignments:history"),
            {"request_id": str(self.first.id)},
        )

        self.assertEqual(response.status_code, 200)
        latest = response.json()["results"][0]
        self.assertEqual(latest["change_type"], "REASSIGNED")
        self.assertEqual(
            latest["previous_assignee"]["id"], str(self.operator.id)
        )
        self.assertEqual(
            latest["new_assignee"]["id"], str(self.other_operator.id)
        )

    def test_invalid_filters_and_json_are_rejected(self):
        force_mfa_login(self.client, self.manager)
        invalid_filter = self.client.get(
            reverse("assignments:request_list"),
            {"assignment_state": "INVALID"},
        )
        invalid_json = self.client.post(
            reverse("assignments:apply"),
            data="{invalid",
            content_type="application/json",
        )
        self.assertEqual(invalid_filter.status_code, 400)
        self.assertEqual(invalid_json.status_code, 400)
