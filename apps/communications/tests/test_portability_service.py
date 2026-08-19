import base64
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Role, UserRole
from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.cases.services.cases import CaseWorkflowService
from apps.cases.services.resolutions import ResolutionService
from apps.communications.services.portability import (
    PortabilityAccessError,
    PortabilityNotAllowedError,
    PortabilityService,
)
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService


ENCRYPTION_KEY = base64.b64encode(b"K" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"L" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
    PORTABILITY_DOWNLOAD_TTL_SECONDS=3600,
    PORTABILITY_RIGHT_CODES=["PORTABILITY"],
)
class PortabilityServiceTests(TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        storage_override = override_settings(
            PRIVATE_STORAGE_ROOT=self.storage.name,
            MEDIA_ROOT=str(Path(self.storage.name).parent / "media-test"),
            STATIC_ROOT=str(Path(self.storage.name).parent / "static-test"),
        )
        storage_override.enable()
        self.addCleanup(storage_override.disable)

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
            code="PORTABILITY",
            name="Portabilidad",
        )
        self.subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Confidencial",
            email="titular@example.test",
            phone="0991234567",
        )
        self.manager = self.create_user("manager@example.test", Role.Code.DPD)
        self.operator = self.create_user("operator@example.test", Role.Code.OPERADOR)
        self.request = CaseWorkflowService.create_request(
            data_subject=self.subject,
            right=self.right,
            request_details="Entregar datos estructurados",
            actor=self.manager,
        )
        self.request = CaseWorkflowService.transition(
            request=self.request,
            target_status=RightsRequest.Status.UNDER_REVIEW,
            actor=self.manager,
        )
        ResolutionService.approve(
            request=self.request,
            details="Procede la entrega portable",
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
        UserRole.objects.create(user=user, role=role, is_primary=True)
        return user

    def test_json_export_is_encrypted_bound_and_audited_without_pii(self):
        generated = PortabilityService.generate(
            request=self.request,
            export_format="JSON",
            actor=self.manager,
        )
        physical = Path(self.storage.name) / generated.export.storage_key
        stored = physical.read_bytes()
        self.assertNotIn(b"Titular Confidencial", stored)
        self.assertNotIn(b"1712345678", stored)
        self.assertTrue(generated.download_token)

        audit = AuditLog.objects.get(action="PORTABILITY_EXPORT_GENERATED")
        serialized = json.dumps(audit.metadata, ensure_ascii=False)
        self.assertNotIn("Titular Confidencial", serialized)
        self.assertNotIn("1712345678", serialized)
        self.assertNotIn(generated.download_token, serialized)
        self.assertNotIn(generated.export.storage_key, serialized)

    def test_download_returns_plaintext_once(self):
        generated = PortabilityService.generate(
            request=self.request,
            export_format="JSON",
            actor=self.manager,
        )
        download = PortabilityService.download(
            export=generated.export,
            token=generated.download_token,
        )
        payload = json.loads(download.content.decode("utf-8"))
        self.assertEqual(payload["data_subject"]["full_name"], "Titular Confidencial")
        self.assertEqual(download.content_type, "application/json")
        self.assertTrue(download.filename.endswith(".json"))

        with self.assertRaises(PortabilityAccessError):
            PortabilityService.download(
                export=generated.export,
                token=generated.download_token,
            )

    def test_csv_export(self):
        generated = PortabilityService.generate(
            request=self.request,
            export_format="csv",
            actor=self.manager,
        )
        download = PortabilityService.download(
            export=generated.export,
            token=generated.download_token,
        )
        text = download.content.decode("utf-8")
        self.assertIn("section,field,value", text)
        self.assertIn("data_subject,full_name,Titular Confidencial", text)
        self.assertEqual(download.content_type, "text/csv; charset=utf-8")

    def test_operator_cannot_generate(self):
        with self.assertRaises(PortabilityAccessError):
            PortabilityService.generate(
                request=self.request,
                export_format="JSON",
                actor=self.operator,
            )

    def test_non_portability_right_is_rejected(self):
        other = RightCatalog.objects.create(code="ACCESS", name="Acceso")
        self.request.right = other
        self.request.save(update_fields=["right", "updated_at"])
        with self.assertRaises(PortabilityNotAllowedError):
            PortabilityService.generate(
                request=self.request,
                export_format="JSON",
                actor=self.manager,
            )

    def test_token_is_bound_to_exact_export(self):
        first = PortabilityService.generate(
            request=self.request,
            export_format="JSON",
            actor=self.manager,
        )
        second = PortabilityService.generate(
            request=self.request,
            export_format="JSON",
            actor=self.manager,
        )
        with self.assertRaises(PortabilityAccessError):
            PortabilityService.download(
                export=second.export,
                token=first.download_token,
            )
        download = PortabilityService.download(
            export=first.export,
            token=first.download_token,
        )
        self.assertTrue(download.content)
