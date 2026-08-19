import base64
import json
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.communications.models import RequestCommunication
from apps.legal_content.models import RightCatalog
from apps.subjects.models import DataSubject


ENCRYPTION_KEY = base64.b64encode(b"C" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
)
class CommunicationHttpTests(TestCase):
    def setUp(self):
        self.right = RightCatalog.objects.create(
            code="COMM_ACCESS", name="Acceso", is_active=True
        )
        self.subject = DataSubject.objects.create(
            subject_type=DataSubject.SubjectType.CUSTOMER,
            document_type=DataSubject.DocumentType.CEDULA,
            document_number_encrypted=b"encrypted-document",
            document_number_lookup_hash="c" * 64,
            full_name_encrypted=b"encrypted-name",
            email_encrypted=b"encrypted-email",
            email_lookup_hash="f" * 64,
        )
        self.manager = self._user("manager-comm@example.test", Role.Code.ADMIN)
        self.operator = self._user(
            "operator-comm@example.test", Role.Code.OPERADOR
        )
        self.auditor = self._user("auditor-comm@example.test", Role.Code.AUDITOR)
        self.outsider = get_user_model().objects.create_user(
            email="outsider-comm@example.test",
            password="StrongCommunicationPassword!593",
            full_name="Sin rol",
            is_active=True,
        )
        self.assigned = self._request("VS-COMM-001", assigned_to=self.operator)
        self.unassigned = self._request("VS-COMM-002")

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongCommunicationPassword!593",
            full_name=f"Usuario {role_code}",
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(user=user, role=role, is_primary=True)
        return user

    def _request(self, reference, assigned_to=None):
        return RightsRequest.objects.create(
            data_subject=self.subject,
            right=self.right,
            reference_number=reference,
            request_details_encrypted=b"encrypted-request",
            subject_snapshot_encrypted=b"encrypted-snapshot",
            status=RightsRequest.Status.UNDER_REVIEW,
            assigned_to=assigned_to,
        )

    def _post(self, url_name, payload):
        return self.client.post(
            reverse(url_name),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_manager_records_encrypted_outbound_and_reads_detail(self):
        force_mfa_login(self.client, self.manager)
        payload = {
            "request_id": str(self.assigned.id),
            "communication_type": "RESPONSE",
            "recipient": "private@example.test",
            "subject": "Respuesta confidencial",
            "body": "Contenido estrictamente reservado",
            "visible_to_subject": True,
        }

        response = self._post("communications:create_outbound", payload)

        self.assertEqual(response.status_code, 201)
        communication = RequestCommunication.objects.get(pk=response.json()["id"])
        stored = b" ".join(
            bytes(value)
            for value in (
                communication.recipient_encrypted,
                communication.subject_encrypted,
                communication.body_encrypted,
            )
        )
        self.assertNotIn(b"private@example.test", stored)
        self.assertNotIn(b"Respuesta confidencial", stored)
        detail = self.client.get(
            reverse("communications:detail", args=[communication.id])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["can_view_content"])
        self.assertEqual(
            detail.json()["content"]["body"], payload["body"]
        )

    def test_inbound_contact_is_encrypted_received_and_audited(self):
        force_mfa_login(self.client, self.manager)
        response = self._post(
            "communications:create_inbound",
            {
                "request_id": str(self.assigned.id),
                "channel": "PHONE",
                "communication_type": "OTHER",
                "contact": "+593991234567",
                "subject": "Consulta telefónica",
                "body": "La persona solicita información de seguimiento.",
                "visible_to_subject": False,
            },
        )

        self.assertEqual(response.status_code, 201)
        communication = RequestCommunication.objects.get(pk=response.json()["id"])
        self.assertEqual(communication.direction, "INBOUND")
        self.assertEqual(communication.delivery_status, "RECEIVED")
        self.assertNotIn(b"+593991234567", bytes(communication.recipient_encrypted))
        self.assertTrue(
            AuditLog.objects.filter(
                action="REQUEST_COMMUNICATION_RECEIVED",
                entity_pk=str(communication.id),
            ).exists()
        )

    def test_operator_scope_is_limited_to_assigned_case(self):
        force_mfa_login(self.client, self.operator)
        allowed = self._post(
            "communications:create_inbound",
            {
                "request_id": str(self.assigned.id),
                "channel": "PORTAL",
                "communication_type": "OTHER",
                "contact": "portal",
                "subject": "Mensaje",
                "body": "Contenido",
            },
        )
        denied = self._post(
            "communications:create_inbound",
            {
                "request_id": str(self.unassigned.id),
                "channel": "PORTAL",
                "communication_type": "OTHER",
                "contact": "portal",
                "subject": "Mensaje",
                "body": "Contenido",
            },
        )
        listing = self.client.get(reverse("communications:list"))

        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(listing.json()["pagination"]["total"], 1)

    def test_auditor_reads_metadata_but_not_decrypted_content(self):
        force_mfa_login(self.client, self.manager)
        created = self._post(
            "communications:create_outbound",
            {
                "request_id": str(self.assigned.id),
                "communication_type": "RESPONSE",
                "recipient": "secret@example.test",
                "subject": "Secreto",
                "body": "Contenido secreto",
            },
        )
        communication_id = created.json()["id"]
        self.client.logout()
        force_mfa_login(self.client, self.auditor)

        detail = self.client.get(
            reverse("communications:detail", args=[communication_id])
        )
        create = self._post(
            "communications:create_outbound",
            {
                "request_id": str(self.assigned.id),
                "communication_type": "RESPONSE",
                "recipient": "blocked@example.test",
                "subject": "No permitido",
                "body": "No permitido",
            },
        )

        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.json()["can_view_content"])
        self.assertIsNone(detail.json()["content"])
        self.assertNotContains(detail, "Contenido secreto")
        self.assertEqual(create.status_code, 403)

    def test_summary_filters_and_never_cache(self):
        force_mfa_login(self.client, self.manager)
        for channel in ("PHONE", "PORTAL"):
            self._post(
                "communications:create_inbound",
                {
                    "request_id": str(self.assigned.id),
                    "channel": channel,
                    "communication_type": "OTHER",
                    "contact": "contacto",
                    "subject": "Consulta",
                    "body": "Contenido",
                },
            )
        summary = self.client.get(reverse("communications:summary"))
        listing = self.client.get(
            reverse("communications:list"), {"channel": "PHONE"}
        )

        self.assertEqual(summary.json()["metrics"]["inbound"], 2)
        self.assertIn("no-cache", summary["Cache-Control"])
        self.assertEqual(listing.json()["pagination"]["total"], 1)

    def test_idempotency_prevents_duplicate_messages(self):
        force_mfa_login(self.client, self.manager)
        key = uuid.uuid4()
        payload = {
            "request_id": str(self.assigned.id),
            "communication_type": "RESPONSE",
            "recipient": "same@example.test",
            "subject": "Mismo mensaje",
            "body": "Contenido",
            "idempotency_key": str(key),
        }
        first = self._post("communications:create_outbound", payload)
        second = self._post("communications:create_outbound", payload)

        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(
            RequestCommunication.objects.filter(idempotency_key=key).count(), 1
        )

    def test_invalid_input_and_outsider_are_rejected(self):
        force_mfa_login(self.client, self.manager)
        invalid = self._post(
            "communications:create_outbound",
            {"request_id": str(self.assigned.id)},
        )
        self.client.logout()
        force_mfa_login(self.client, self.outsider)
        forbidden = self.client.get(reverse("communications:summary"))

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(forbidden.status_code, 403)
