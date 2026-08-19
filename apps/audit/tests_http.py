import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService


ENCRYPTION_KEY = base64.b64encode(b"J" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
)
class AuditHttpTests(TestCase):
    def setUp(self):
        self.admin = self._user("audit-admin@example.test", Role.Code.ADMIN)
        self.auditor = self._user(
            "audit-reader@example.test",
            Role.Code.AUDITOR,
        )
        self.responsible = self._user(
            "audit-responsible@example.test",
            Role.Code.RESPONSABLE,
        )
        self.first = AuditService.write(
            actor_type=AuditLog.ActorType.SYSTEM,
            actor=None,
            source=AuditLog.Source.SYSTEM,
            action="SYSTEM_BOOTSTRAP",
            entity_type="SYSTEM",
        )
        self.second = AuditService.write(
            actor_type=AuditLog.ActorType.USER,
            actor=self.admin,
            source=AuditLog.Source.WEB,
            action="REQUEST_CREATED",
            entity_type="RIGHTS_REQUEST",
            entity_pk="VS-AUDIT-001",
            reason="Motivo interno cifrado",
            metadata={
                "status": "RECEIVED",
                "email": "subject@example.test",
            },
            ip_address="127.0.0.1",
            user_agent="Audit test agent",
        )
        self.third = AuditService.write(
            actor_type=AuditLog.ActorType.SYSTEM,
            actor=None,
            source=AuditLog.Source.COMMAND,
            action="REPORT_EXPORTED",
            entity_type="REPORT",
        )

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongAuditPassword!593",
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

    def test_auditor_can_filter_and_page_safe_event_headers(self):
        force_mfa_login(self.client, self.auditor)

        response = self.client.get(
            reverse("audit:event_list"),
            {
                "action": " request_created ",
                "entity_type": "rights_request",
                "source": AuditLog.Source.WEB,
                "actor": str(self.admin.id),
                "correlation_id": str(self.second.correlation_id),
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-cache", response["Cache-Control"])
        payload = response.json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["events"][0]["action"], "REQUEST_CREATED")
        serialized = response.content.decode("utf-8")
        self.assertNotIn("metadata", serialized)
        self.assertNotIn("reason", serialized)
        self.assertNotIn("subject@example.test", serialized)

    def test_audit_page_renders_safe_event_headers_and_detail(self):
        force_mfa_login(self.client, self.auditor)

        response = self.client.get(
            reverse("audit:index"),
            {"event": self.second.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auditoría")
        self.assertContains(response, "REQUEST_CREATED")
        self.assertContains(response, "127.0.0.1")
        self.assertNotContains(response, "subject@example.test")
        self.assertNotContains(response, "Motivo interno cifrado")
        self.assertIn("no-cache", response["Cache-Control"])

    def test_detail_is_sanitized_and_never_returns_encrypted_reason(self):
        force_mfa_login(self.client, self.admin)

        response = self.client.get(
            reverse("audit:event_detail", args=[self.second.id])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["metadata"]["email"], "[REDACTED]")
        self.assertEqual(payload["ip_address"], "127.0.0.1")
        self.assertEqual(payload["user_agent"], "Audit test agent")
        self.assertNotIn("reason_encrypted", payload)
        self.assertNotContains(response, "Motivo interno cifrado")

    def test_export_contains_headers_but_not_event_detail(self):
        force_mfa_login(self.client, self.auditor)

        response = self.client.get(reverse("audit:export_csv"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Export-Limit"], "5000")
        content = response.content.decode("utf-8-sig")
        self.assertIn("REQUEST_CREATED", content)
        self.assertIn("Correlation ID", content)
        self.assertNotIn("subject@example.test", content)
        self.assertNotIn("127.0.0.1", content)
        self.assertNotIn("Audit test agent", content)

    def test_integrity_endpoint_accepts_valid_chain(self):
        force_mfa_login(self.client, self.auditor)

        response = self.client.get(reverse("audit:integrity"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "valid": True,
                "chain_scope": "GLOBAL",
                "checked_entries": 3,
            },
        )

    def test_integrity_endpoint_reports_tampering_without_payload(self):
        AuditLog.objects.filter(pk=self.second.pk).update(
            metadata={"status": "TAMPERED"}
        )
        force_mfa_login(self.client, self.auditor)

        response = self.client.get(reverse("audit:integrity"))

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["valid"])
        self.assertEqual(response.json()["chain_position"], 2)
        self.assertNotContains(
            response,
            "entry_hash mismatch",
            status_code=409,
        )

    def test_invalid_filter_is_rejected_after_authorization(self):
        force_mfa_login(self.client, self.auditor)

        response = self.client.get(
            reverse("audit:event_list"),
            {
                "date_from": timezone.now().date().isoformat(),
                "date_to": "2025-01-01",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("__all__", response.json()["errors"])

    def test_unauthenticated_and_unauthorized_access_is_rejected(self):
        url = reverse("audit:event_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        force_mfa_login(self.client, self.responsible)
        response = self.client.get(url, {"date_from": "invalid"})
        self.assertEqual(response.status_code, 403)
