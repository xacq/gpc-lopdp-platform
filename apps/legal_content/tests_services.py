import base64
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Role, UserRole
from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.cases.services.cases import CaseWorkflowService
from apps.legal_content.models import LegalDocument, RightCatalog
from apps.legal_content.services.documents import (
    LegalDocumentPermissionError,
    LegalDocumentService,
    LegalDocumentStateError,
    NoticeDeliveryService,
)
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService


ENCRYPTION_KEY = base64.b64encode(b"L" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"M" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
)
class LegalDocumentServiceTests(TestCase):
    def setUp(self):
        SystemSetting.objects.create(
            legal_name="VINESA S.A.", trade_name="VINESA",
            ruc="1792049598001", domain="privacidad.vinesa.test",
            contact_email="privacidad@example.test", request_prefix="VS",
            timezone="America/Guayaquil",
        )
        self.admin = self.create_user("admin@example.test", Role.Code.ADMIN)
        self.dpd = self.create_user("dpd@example.test", Role.Code.DPD)
        self.operator = self.create_user("operator@example.test", Role.Code.OPERADOR)

    def create_user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email, password="TestPassword123!", full_name=email,
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(
            user=user, role=role, assigned_by=user, is_primary=True,
        )
        return user

    def draft(self, *, version="1.0", effective_from=None, actor=None):
        return LegalDocumentService.create_draft(
            document_type=LegalDocument.DocumentType.PRIVACY_POLICY,
            title="Política de Privacidad",
            version=version,
            content_html=(
                '<h2 onclick="steal()">Privacidad</h2>'
                '<script>alert(1)</script><p>Contenido <strong>aprobado</strong>.</p>'
                '<a href="javascript:alert(2)">enlace</a>'
            ),
            effective_from=effective_from or timezone.now(),
            actor=actor or self.admin,
        )

    def test_draft_sanitizes_html_hashes_and_audits_without_content(self):
        document = self.draft()
        self.assertNotIn("script", document.content_html)
        self.assertNotIn("onclick", document.content_html)
        self.assertNotIn("javascript:", document.content_html)
        self.assertEqual(len(document.content_sha256), 64)
        audit = AuditLog.objects.get(action="LEGAL_DOCUMENT_DRAFT_CREATED")
        self.assertNotIn("Contenido", str(audit.new_values))

    def test_publish_supersedes_open_version_and_current_is_time_aware(self):
        first = self.draft(
            version="1.0",
            effective_from=timezone.now() - timedelta(days=2),
        )
        LegalDocumentService.publish(document=first, actor=self.dpd)
        second = self.draft(
            version="2.0",
            effective_from=timezone.now() + timedelta(days=1),
        )
        LegalDocumentService.publish(document=second, actor=self.dpd)

        first.refresh_from_db()
        self.assertEqual(first.effective_to, second.effective_from)
        self.assertEqual(
            LegalDocumentService.current(
                document_type=LegalDocument.DocumentType.PRIVACY_POLICY
            ).id,
            first.id,
        )
        self.assertEqual(
            LegalDocumentService.current(
                document_type=LegalDocument.DocumentType.PRIVACY_POLICY,
                at=second.effective_from + timedelta(seconds=1),
            ).id,
            second.id,
        )

    def test_operator_cannot_manage_legal_documents(self):
        with self.assertRaises(LegalDocumentPermissionError):
            self.draft(actor=self.operator)

    def test_cannot_publish_older_version_over_open_version(self):
        first = self.draft(version="2.0")
        LegalDocumentService.publish(document=first, actor=self.admin)
        older = self.draft(
            version="1.0",
            effective_from=first.effective_from - timedelta(days=1),
        )
        with self.assertRaises(LegalDocumentStateError):
            LegalDocumentService.publish(document=older, actor=self.admin)

    def test_notice_delivery_records_rendered_hash_and_no_rendered_content(self):
        document = self.draft()
        LegalDocumentService.publish(document=document, actor=self.admin)
        right = RightCatalog.objects.create(code="ACCESS", name="Acceso")
        subject = SubjectService.create(
            subject_type="CUSTOMER", document_type="CEDULA",
            document_number="1712345678", full_name="Titular",
            email="subject@example.test",
        )
        request = CaseWorkflowService.create_request(
            data_subject=subject, right=right,
            request_details="Detalle", source_channel=RightsRequest.SourceChannel.WEB,
            actor=self.admin,
        )
        rendered = "<p>Aviso exacto mostrado</p>"
        delivery = NoticeDeliveryService.record(
            request=request,
            legal_document=document,
            rendered_content=rendered,
            acknowledged=True,
        )
        self.assertEqual(len(delivery.rendered_content_sha256), 64)
        audit = AuditLog.objects.get(action="NOTICE_DELIVERY_RECORDED")
        self.assertNotIn("Aviso exacto", str(audit.new_values))
