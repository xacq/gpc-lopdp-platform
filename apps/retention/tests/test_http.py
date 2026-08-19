import base64
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.legal_content.models import RightCatalog
from apps.retention.models import DataDisposalEvent, RetentionRule
from apps.subjects.models import DataSubject


ENCRYPTION_KEY = base64.b64encode(b"R" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
)
class RetentionHttpTests(TestCase):
    def setUp(self):
        self.manager = self._user("manager-ret@example.test", Role.Code.DPD)
        self.operator = self._user("operator-ret@example.test", Role.Code.OPERADOR)
        self.auditor = self._user("auditor-ret@example.test", Role.Code.AUDITOR)
        self.rule = RetentionRule.objects.create(
            entity_type="RIGHTS_REQUEST",
            retention_days=30,
            retention_anchor=RetentionRule.RetentionAnchor.CLOSED_AT,
            final_action=RetentionRule.FinalAction.ARCHIVE,
            requires_approval=True,
            is_active=True,
        )
        self.pending = DataDisposalEvent.objects.create(
            retention_rule=self.rule,
            entity_type="RIGHTS_REQUEST",
            entity_pk="case-pending",
            action=DataDisposalEvent.Action.ARCHIVE,
            status=DataDisposalEvent.Status.PENDING_APPROVAL,
        )

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongRetentionPassword!593",
            full_name=f"Usuario {role_code}",
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(user=user, role=role, is_primary=True)
        return user

    def test_manager_reads_summary_and_filtered_events(self):
        force_mfa_login(self.client, self.manager)
        summary = self.client.get(reverse("retention:summary"))
        listing = self.client.get(
            reverse("retention:event_list"),
            {"status": "PENDING_APPROVAL"},
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["metrics"]["pending_approval"], 1)
        self.assertIn("no-cache", summary["Cache-Control"])
        self.assertEqual(listing.json()["pagination"]["total"], 1)
        self.assertEqual(listing.json()["results"][0]["entity_pk"], "case-pending")

    def test_panel_renders_and_approves_with_html_redirect(self):
        force_mfa_login(self.client, self.manager)

        panel = self.client.get(reverse("retention:panel"))
        response = self.client.post(
            reverse("retention:approve", args=[self.pending.id]),
            {"return_to": "panel"},
        )

        self.assertEqual(panel.status_code, 200)
        self.assertContains(panel, "Ciclo de vida de datos")
        self.assertContains(panel, "case-pending")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("retention:panel"))
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, DataDisposalEvent.Status.APPROVED)

    def test_operator_and_auditor_are_forbidden(self):
        for user in (self.operator, self.auditor):
            force_mfa_login(self.client, user)
            self.assertEqual(
                self.client.get(reverse("retention:summary")).status_code, 403
            )
            self.client.logout()

    def test_manager_approves_and_rejects_with_audit(self):
        force_mfa_login(self.client, self.manager)
        approved = self.client.post(
            reverse("retention:approve", args=[self.pending.id])
        )
        rejected = self.client.post(
            reverse("retention:reject", args=[self.pending.id])
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"]["code"], "APPROVED")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["status"]["code"], "REJECTED")
        self.assertTrue(
            AuditLog.objects.filter(
                entity_pk=str(self.pending.id),
                action="DATA_DISPOSAL_EVENT_REJECTED",
            ).exists()
        )

    def test_invalid_transition_returns_conflict(self):
        self.pending.status = DataDisposalEvent.Status.EXECUTED
        self.pending.executed_at = timezone.now()
        self.pending.save(update_fields=["status", "executed_at"])
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse("retention:approve", args=[self.pending.id])
        )
        self.assertEqual(response.status_code, 409)

    def test_failed_event_can_be_prepared_for_retry(self):
        self.pending.status = DataDisposalEvent.Status.FAILED
        self.pending.approved_at = timezone.now()
        self.pending.error_code = "RETENTION_EXECUTION_FAILED"
        self.pending.error_message = "RuntimeError"
        self.pending.save(
            update_fields=["status", "approved_at", "error_code", "error_message"]
        )
        force_mfa_login(self.client, self.manager)
        response = self.client.post(
            reverse("retention:retry", args=[self.pending.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"]["code"], "APPROVED")
        self.assertIsNone(response.json()["error_code"])


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
)
class RetentionDetectionCommandTests(TestCase):
    def test_command_detects_eligible_closed_case_without_pii_output(self):
        rule = RetentionRule.objects.create(
            entity_type="RIGHTS_REQUEST",
            retention_days=1,
            retention_anchor=RetentionRule.RetentionAnchor.CLOSED_AT,
            final_action=RetentionRule.FinalAction.ARCHIVE,
            requires_approval=True,
            is_active=True,
        )
        right = RightCatalog.objects.create(
            code="RETENTION_RIGHT", name="Acceso", is_active=True
        )
        subject = DataSubject.objects.create(
            subject_type=DataSubject.SubjectType.CUSTOMER,
            document_type=DataSubject.DocumentType.CEDULA,
            document_number_encrypted=b"private-document",
            document_number_lookup_hash="a" * 64,
            full_name_encrypted=b"private-name",
            email_encrypted=b"private-email",
            email_lookup_hash="b" * 64,
        )
        case = RightsRequest.objects.create(
            data_subject=subject,
            right=right,
            reference_number="VS-RET-CMD-001",
            request_details_encrypted=b"private-request",
            subject_snapshot_encrypted=b"private-snapshot",
            status=RightsRequest.Status.CLOSED,
            received_at=timezone.now() - timedelta(days=3),
            closed_at=timezone.now() - timedelta(days=2),
        )
        output = StringIO()

        call_command("detect_retention_events", stdout=output, no_color=True)

        self.assertTrue(
            DataDisposalEvent.objects.filter(
                retention_rule=rule,
                entity_pk=str(case.id),
                status=DataDisposalEvent.Status.PENDING_APPROVAL,
            ).exists()
        )
        rendered = output.getvalue()
        self.assertIn("eventos=1", rendered)
        self.assertNotIn(case.reference_number, rendered)
