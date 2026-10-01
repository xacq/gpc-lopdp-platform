import base64
import json
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.tests_helpers import force_mfa_login
from apps.cases.models import RightsRequest
from apps.core.services.crypto import CryptoService
from apps.evidence.models import RequestAttachment
from apps.legal_content.models import RightCatalog
from apps.subjects.models import DataSubject


ENCRYPTION_KEY = base64.b64encode(b"E" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
)
class EvidenceHttpTests(TestCase):
    def setUp(self):
        self.right = RightCatalog.objects.create(
            code="EVIDENCE_ACCESS", name="Acceso", is_active=True
        )
        self.subject = DataSubject.objects.create(
            subject_type=DataSubject.SubjectType.CUSTOMER,
            document_type=DataSubject.DocumentType.CEDULA,
            document_number_encrypted=b"private-document",
            document_number_lookup_hash="1" * 64,
            full_name_encrypted=b"private-name",
            email_encrypted=b"private-email",
            email_lookup_hash="2" * 64,
        )
        self.manager = self._user("manager-evidence@example.test", Role.Code.DPD)
        self.operator = self._user(
            "operator-evidence@example.test", Role.Code.OPERADOR
        )
        self.auditor = self._user(
            "auditor-evidence@example.test", Role.Code.AUDITOR
        )
        self.outsider = get_user_model().objects.create_user(
            email="outsider-evidence@example.test",
            password="StrongEvidencePassword!593",
            full_name="Sin rol",
            is_active=True,
        )
        self.case = self._case("VS-EVI-001", self.operator)
        self.other_case = self._case("VS-EVI-002", None)

    def _user(self, email, role_code):
        user = get_user_model().objects.create_user(
            email=email,
            password="StrongEvidencePassword!593",
            full_name=f"Usuario {role_code}",
            is_active=True,
        )
        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={"name": role_code, "is_active": True},
        )
        UserRole.objects.create(user=user, role=role, is_primary=True)
        return user

    def _case(self, reference, assigned_to):
        return RightsRequest.objects.create(
            data_subject=self.subject,
            right=self.right,
            reference_number=reference,
            request_details_encrypted=b"private-request",
            subject_snapshot_encrypted=b"private-snapshot",
            status=RightsRequest.Status.UNDER_REVIEW,
            assigned_to=assigned_to,
        )

    def _post_verification(self, case, result="VERIFIED"):
        return self.client.post(
            reverse("evidence:identity_create"),
            data=json.dumps(
                {
                    "request_id": str(case.id),
                    "verification_method": "MANUAL",
                    "result": result,
                    "validation_notes": "Documento revisado de forma confidencial",
                }
            ),
            content_type="application/json",
        )

    def test_manager_records_and_lists_encrypted_identity_notes(self):
        force_mfa_login(self.client, self.manager)
        created = self._post_verification(self.case)
        listing = self.client.get(
            reverse("evidence:identity_list"),
            {"request_id": str(self.case.id)},
        )
        self.case.refresh_from_db()
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.case.identity_status, "VERIFIED")
        self.assertEqual(len(listing.json()["results"]), 1)
        self.assertEqual(
            listing.json()["results"][0]["validation_notes"],
            "Documento revisado de forma confidencial",
        )

    def test_case_panel_records_verification_and_redirects(self):
        force_mfa_login(self.client, self.operator)

        response = self.client.post(
            reverse("evidence:case_panel", args=[self.case.id]),
            {
                "verification_method": "MANUAL",
                "result": "VERIFIED",
                "validation_notes": "Validación realizada desde el panel.",
            },
        )

        self.assertEqual(response.status_code, 302)
        panel = self.client.get(
            reverse("evidence:case_panel", args=[self.case.id])
        )
        self.assertEqual(panel.status_code, 200)
        self.assertContains(panel, "Historial de verificaciones")
        self.assertContains(panel, "Validación realizada desde el panel.")
        self.assertIn("no-cache", panel["Cache-Control"])

    def test_operator_can_modify_only_assigned_case(self):
        force_mfa_login(self.client, self.operator)
        allowed = self._post_verification(self.case)
        denied = self._post_verification(self.other_case)
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(denied.status_code, 404)

    def test_auditor_sees_history_without_sensitive_notes_and_is_read_only(self):
        force_mfa_login(self.client, self.manager)
        self._post_verification(self.case)
        self.client.logout()
        force_mfa_login(self.client, self.auditor)
        listing = self.client.get(
            reverse("evidence:identity_list"),
            {"request_id": str(self.case.id)},
        )
        create = self._post_verification(self.case, "REJECTED")
        row = listing.json()["results"][0]
        self.assertEqual(listing.status_code, 200)
        self.assertFalse(row["can_view_sensitive"])
        self.assertIsNone(row["validation_notes"])
        self.assertIsNone(row["validation_metadata"])
        self.assertEqual(create.status_code, 403)

        panel = self.client.get(
            reverse("evidence:case_panel", args=[self.case.id])
        )
        self.assertEqual(panel.status_code, 200)
        self.assertNotContains(panel, "Documento revisado de forma confidencial")
        self.assertNotContains(panel, "Registrar verificación de identidad")

    def test_attachment_filename_is_hidden_from_auditor(self):
        attachment_id = uuid.uuid4()
        encrypted_name = CryptoService.encrypt_text(
            "identidad-confidencial.pdf",
            aad=(
                f"request_attachments:{attachment_id}:original_filename"
            ),
            key_version=1,
        )
        RequestAttachment.objects.create(
            id=attachment_id,
            request=self.case,
            attachment_type=RequestAttachment.AttachmentType.IDENTITY_DOCUMENT,
            visibility=RequestAttachment.Visibility.INTERNAL,
            original_filename_encrypted=encrypted_name.data,
            storage_backend=RequestAttachment.StorageBackend.LOCAL,
            storage_key=f"attachments/{self.case.id}/{attachment_id}.bin",
            mime_type="application/pdf",
            size_bytes=10,
            file_sha256="a" * 64,
            is_encrypted=True,
            encryption_key_version=1,
            malware_scan_status=RequestAttachment.MalwareScanStatus.CLEAN,
            uploaded_by=self.manager,
        )
        force_mfa_login(self.client, self.auditor)
        auditor = self.client.get(
            reverse("evidence:attachment_list"),
            {"request_id": str(self.case.id)},
        )
        self.client.logout()
        force_mfa_login(self.client, self.manager)
        manager = self.client.get(
            reverse("evidence:attachment_list"),
            {"request_id": str(self.case.id)},
        )
        self.assertIsNone(auditor.json()["results"][0]["filename"])
        self.assertFalse(auditor.json()["results"][0]["can_download"])
        self.assertEqual(
            auditor.json()["results"][0]["malware_scan_status"],
            {"code": "CLEAN", "label": "Limpio"},
        )
        self.assertEqual(
            manager.json()["results"][0]["filename"],
            "identidad-confidencial.pdf",
        )

        panel = self.client.get(
            reverse("evidence:case_panel", args=[self.case.id])
        )
        self.assertContains(panel, "Limpio")
        self.assertNotContains(panel, ">CLEAN<", html=False)

    def test_user_without_panel_role_is_forbidden(self):
        force_mfa_login(self.client, self.outsider)
        response = self.client.get(
            reverse("evidence:identity_list"),
            {"request_id": str(self.case.id)},
        )
        self.assertEqual(response.status_code, 403)
