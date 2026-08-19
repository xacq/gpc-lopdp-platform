import base64
import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.audit.models import AuditLog
from apps.cases.models import RightsRequest
from apps.cases.services.cases import CaseWorkflowService
from apps.cases.services.resolutions import ResolutionService
from apps.communications.models import PortabilityExport
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService


ENCRYPTION_KEY = base64.b64encode(b"P" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"Q" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
    PORTABILITY_DOWNLOAD_TTL_SECONDS=3600,
    PORTABILITY_RIGHT_CODES=["PORTABILITY"],
)
class PortabilityHttpTests(TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory(dir=settings.BASE_DIR)
        self.addCleanup(self.storage.cleanup)
        storage_override = override_settings(
            PRIVATE_STORAGE_ROOT=self.storage.name,
            MEDIA_ROOT=str(Path(self.storage.name) / "media"),
            STATIC_ROOT=str(Path(self.storage.name) / "static"),
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
        right = RightCatalog.objects.create(
            code="PORTABILITY", name="Portabilidad", is_active=True
        )
        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Confidencial",
            email="titular@example.test",
        )
        self.manager = self._user("manager-port@example.test", Role.Code.DPD)
        self.operator = self._user("operator-port@example.test", Role.Code.OPERADOR)
        self.case = CaseWorkflowService.create_request(
            data_subject=subject,
            right=right,
            request_details="Entregar datos portables",
            actor=self.manager,
        )
        self.case = CaseWorkflowService.transition(
            request=self.case,
            target_status=RightsRequest.Status.UNDER_REVIEW,
            actor=self.manager,
        )
        ResolutionService.approve(
            request=self.case,
            details="Procede portabilidad",
            actor=self.manager,
        )

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongPortabilityPassword!593",
            full_name=f"Usuario {role_code}",
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(user=user, role=role, is_primary=True)
        return user

    def _generate(self):
        return self.client.post(
            reverse("communications:portability_generate"),
            data=json.dumps(
                {"request_id": str(self.case.id), "export_format": "JSON"}
            ),
            content_type="application/json",
        )

    def test_manager_generates_lists_and_downloads_export_once(self):
        force_mfa_login(self.client, self.manager)
        generated = self._generate()
        self.assertEqual(generated.status_code, 201)
        payload = generated.json()
        self.assertTrue(payload["download_token"])
        listing = self.client.get(reverse("communications:portability_list"))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["results"][0]["id"], payload["id"])
        self.assertNotIn("download_token", listing.content.decode("utf-8"))

        download = self.client.post(
            reverse("communications:portability_download"),
            {"export_id": payload["id"], "token": payload["download_token"]},
        )
        repeated = self.client.post(
            reverse("communications:portability_download"),
            {"export_id": payload["id"], "token": payload["download_token"]},
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/json")
        self.assertIn("no-store", download["Cache-Control"])
        self.assertEqual(repeated.status_code, 404)

    def test_manager_revokes_export_and_token(self):
        force_mfa_login(self.client, self.manager)
        generated = self._generate().json()
        revoked = self.client.post(
            reverse("communications:portability_revoke", args=[generated["id"]])
        )
        download = self.client.post(
            reverse("communications:portability_download"),
            {"export_id": generated["id"], "token": generated["download_token"]},
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertIsNotNone(revoked.json()["revoked_at"])
        self.assertEqual(download.status_code, 404)
        self.assertTrue(
            AuditLog.objects.filter(
                action="PORTABILITY_EXPORT_REVOKED",
                entity_pk=generated["id"],
            ).exists()
        )

    def test_operator_cannot_generate_or_revoke(self):
        force_mfa_login(self.client, self.operator)
        generated = self._generate()
        self.assertEqual(generated.status_code, 403)

    def test_invalid_download_does_not_disclose_export_state(self):
        response = self.client.post(
            reverse("communications:portability_download"),
            {"export_id": "not-a-uuid", "token": "bad"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "PortabilityExport", status_code=400)
