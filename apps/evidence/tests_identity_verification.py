import base64
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Role, UserRole
from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.cases.services.cases import CaseWorkflowService
from apps.evidence.models import IdentityVerification
from apps.evidence.services.identity import (
    IdentityVerificationPermissionError,
    IdentityVerificationService,
    IdentityVerificationStateError,
)
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService


ENCRYPTION_KEY = base64.b64encode(b"I" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"J" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
)
class IdentityVerificationServiceTests(TestCase):
    def setUp(self):
        SystemSetting.objects.create(
            legal_name="VINESA S.A.",
            trade_name="VINESA",
            ruc="1792049598001",
            domain="privacidad.vinesa.test",
            contact_email="privacidad@example.test",
            request_prefix="VS",
            timezone="America/Guayaquil",
        )
        self.right = RightCatalog.objects.create(
            code="ACCESS",
            name="Acceso",
        )
        self.subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Confidencial",
            email="titular@example.test",
        )
        self.manager = self.create_user("manager@example.test", Role.Code.DPD)
        self.operator = self.create_user("operator@example.test", Role.Code.OPERADOR)
        self.auditor = self.create_user("auditor@example.test", Role.Code.AUDITOR)
        self.request = CaseWorkflowService.create_request(
            data_subject=self.subject,
            right=self.right,
            request_details="Solicitud privada",
            source_channel=RightsRequest.SourceChannel.WEB,
            actor=self.manager,
        )

    def create_user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="TestPassword123!",
            full_name=email,
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(
            user=user,
            role=role,
            assigned_by=user,
            is_primary=True,
        )
        return user

    def test_records_encrypted_notes_updates_status_and_audits_without_pii(self):
        verification = IdentityVerificationService.record(
            request=self.request,
            verification_method="DOCUMENT_REVIEW",
            result="VERIFIED",
            actor=self.manager,
            validation_notes="Cédula revisada para Titular Confidencial",
            validation_metadata={
                "document_number": "1712345678",
                "check": "manual",
            },
        )

        self.request.refresh_from_db()
        self.assertEqual(
            self.request.identity_status,
            RightsRequest.IdentityStatus.VERIFIED,
        )
        self.assertNotIn(
            b"Titular Confidencial",
            verification.validation_notes_encrypted,
        )
        self.assertEqual(
            IdentityVerificationService.decrypt_notes(
                verification=verification,
                actor=self.manager,
            ),
            "Cédula revisada para Titular Confidencial",
        )
        self.assertEqual(
            verification.validation_metadata["document_number"],
            "[REDACTED]",
        )
        audit = AuditLog.objects.get(
            action="IDENTITY_VERIFICATION_RECORDED"
        )
        serialized = json.dumps(
            {
                "description": audit.description,
                "previous": audit.previous_values,
                "new": audit.new_values,
                "metadata": audit.metadata,
            },
            ensure_ascii=False,
        )
        self.assertNotIn("1712345678", serialized)
        self.assertNotIn("Titular Confidencial", serialized)

    def test_inconclusive_maps_to_requires_review_and_preserves_history(self):
        first = IdentityVerificationService.record(
            request=self.request,
            verification_method="STRUCTURAL_DOCUMENT_CHECK",
            result="INCONCLUSIVE",
            actor=self.manager,
        )
        second = IdentityVerificationService.record(
            request=self.request,
            verification_method="MANUAL",
            result="REJECTED",
            actor=self.manager,
        )

        self.request.refresh_from_db()
        self.assertEqual(
            self.request.identity_status,
            RightsRequest.IdentityStatus.REJECTED,
        )
        self.assertEqual(
            set(
                IdentityVerification.objects.filter(
                    request=self.request
                ).values_list("id", flat=True)
            ),
            {first.id, second.id},
        )

    def test_assigned_operator_can_verify_but_unassigned_operator_cannot(self):
        self.request.assigned_to = self.operator
        self.request.save(update_fields=["assigned_to", "updated_at"])
        IdentityVerificationService.record(
            request=self.request,
            verification_method="MANUAL",
            result="VERIFIED",
            actor=self.operator,
        )

        other_request = CaseWorkflowService.create_request(
            data_subject=self.subject,
            right=self.right,
            request_details="Otra solicitud",
            source_channel=RightsRequest.SourceChannel.WEB,
            actor=self.manager,
        )
        with self.assertRaises(IdentityVerificationPermissionError):
            IdentityVerificationService.record(
                request=other_request,
                verification_method="MANUAL",
                result="VERIFIED",
                actor=self.operator,
            )

    def test_auditor_is_read_only_and_cannot_decrypt_notes(self):
        verification = IdentityVerificationService.record(
            request=self.request,
            verification_method="MANUAL",
            result="VERIFIED",
            actor=self.manager,
            validation_notes="Nota restringida",
        )
        with self.assertRaises(IdentityVerificationPermissionError):
            IdentityVerificationService.record(
                request=self.request,
                verification_method="MANUAL",
                result="REJECTED",
                actor=self.auditor,
            )
        with self.assertRaises(IdentityVerificationPermissionError):
            IdentityVerificationService.decrypt_notes(
                verification=verification,
                actor=self.auditor,
            )

    def test_terminal_request_cannot_be_changed(self):
        self.request.status = RightsRequest.Status.CLOSED
        self.request.save(update_fields=["status", "updated_at"])
        with self.assertRaises(IdentityVerificationStateError):
            IdentityVerificationService.record(
                request=self.request,
                verification_method="MANUAL",
                result="VERIFIED",
                actor=self.manager,
            )
