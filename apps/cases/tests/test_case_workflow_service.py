import base64
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.cases.models import (
    RequestStatusHistory,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseConfigurationError,
    CaseWorkflowService,
    InactiveRightError,
    RepresentativeSubjectMismatchError,
)
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import (
    RepresentativeService,
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"C" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"D" * 32
).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={
        1: ENCRYPTION_KEY,
    },
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={
        1: LOOKUP_KEY,
    },
)
class CaseWorkflowServiceTests(TestCase):

    def setUp(self):
        self.setting = (
            SystemSetting.objects.create(
                legal_name=(
                    "VINOS Y ESPIRITUOSOS "
                    "VINESA S.A."
                ),
                trade_name="VINESA",
                ruc="1792049598001",
                domain=(
                    "privacidad.vinesa.test"
                ),
                contact_email=(
                    "privacidad@vinesa.com.ec"
                ),
                request_prefix="VINESA",
                timezone=(
                    "America/Guayaquil"
                ),
            )
        )

        self.right = (
            RightCatalog.objects.create(
                code="TEST_RIGHT",
                name="Derecho de prueba",
                is_active=True,
            )
        )

        self.subject = (
            SubjectService.create(
                subject_type="CUSTOMER",
                document_type="CEDULA",
                document_number="1712345678",
                full_name=(
                    "Titular Prueba"
                ),
                email=(
                    "subject@example.com"
                ),
                phone=(
                    "+593991234567"
                ),
            )
        )

    def create_actor(self):
        user_model = get_user_model()

        return user_model.objects.create_user(
            email=(
                "operator@example.com"
            ),
            password=(
                "TestPassword123!"
            ),
            full_name=(
                "Operador Prueba"
            ),
            is_active=True,
        )

    def test_create_request_initializes_case(self):
        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details=(
                    "Necesito ejercer "
                    "mi derecho."
                ),
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .RECEIVED,
        )
        self.assertEqual(
            request.identity_status,
            RightsRequest
            .IdentityStatus
            .PENDING,
        )
        self.assertEqual(
            request.source_channel,
            RightsRequest
            .SourceChannel
            .WEB,
        )
        self.assertIsNone(
            request.assigned_to
        )

        self.assertRegex(
            request.reference_number,
            (
                r"^VINESA-\d{4}-"
                r"\d{6,}$"
            ),
        )

    def test_request_details_are_encrypted(self):
        plaintext = (
            "Detalle sensible "
            "de la solicitud."
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details=plaintext,
            )
        )

        request.refresh_from_db()

        self.assertNotIn(
            plaintext.encode("utf-8"),
            bytes(
                request
                .request_details_encrypted
            ),
        )

        decrypted = (
            CaseWorkflowService
            .decrypt_request_details(
                request
            )
        )

        self.assertEqual(
            decrypted,
            plaintext,
        )

    def test_subject_snapshot_is_encrypted_and_stable(self):
        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        request.refresh_from_db()

        self.assertNotIn(
            b"subject@example.com",
            bytes(
                request
                .subject_snapshot_encrypted
            ),
        )

        snapshot = (
            CaseWorkflowService
            .decrypt_subject_snapshot(
                request
            )
        )

        self.assertEqual(
            snapshot.subject_id,
            self.subject.id,
        )
        self.assertEqual(
            snapshot.document_number,
            "1712345678",
        )
        self.assertEqual(
            snapshot.full_name,
            "Titular Prueba",
        )
        self.assertEqual(
            snapshot.email,
            "subject@example.com",
        )

    def test_initial_history_is_created(self):
        actor = self.create_actor()

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
                actor=actor,
            )
        )

        history = (
            RequestStatusHistory.objects
            .get(request=request)
        )

        self.assertIsNone(
            history.previous_status
        )
        self.assertEqual(
            history.new_status,
            RightsRequest
            .Status
            .RECEIVED,
        )
        self.assertEqual(
            history.changed_by_id,
            actor.id,
        )
        self.assertEqual(
            history.change_source,
            RequestStatusHistory
            .ChangeSource
            .WEB,
        )

    def test_creation_generates_audit_entry_without_pii(self):
        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details=(
                    "Contenido privado."
                ),
            )
        )

        audit = AuditLog.objects.get(
            entity_type="RIGHTS_REQUEST",
            entity_pk=str(request.id),
            action=(
                "RIGHTS_REQUEST_CREATED"
            ),
        )

        self.assertEqual(
            audit.actor_type,
            AuditLog.ActorType.SYSTEM,
        )
        self.assertEqual(
            audit.metadata[
                "reference_number"
            ],
            request.reference_number,
        )

        serialized_metadata = str(
            audit.metadata
        )

        self.assertNotIn(
            "subject@example.com",
            serialized_metadata,
        )
        self.assertNotIn(
            "1712345678",
            serialized_metadata,
        )
        self.assertNotIn(
            "Titular Prueba",
            serialized_metadata,
        )

    def test_representative_must_belong_to_subject(self):
        other_subject = (
            SubjectService.create(
                subject_type="CUSTOMER",
                document_type="CEDULA",
                document_number=(
                    "1712345679"
                ),
                full_name=(
                    "Otro Titular"
                ),
                email=(
                    "other@example.com"
                ),
            )
        )

        representative = (
            RepresentativeService.create(
                data_subject=other_subject,
                representative_name=(
                    "Representante"
                ),
                representative_document_type=(
                    "CEDULA"
                ),
                representative_document_number=(
                    "0912345678"
                ),
            )
        )

        with self.assertRaises(
            RepresentativeSubjectMismatchError
        ):
            (
                CaseWorkflowService
                .create_request(
                    data_subject=(
                        self.subject
                    ),
                    right=self.right,
                    representative=(
                        representative
                    ),
                    request_details=(
                        "Prueba"
                    ),
                )
            )

        self.assertEqual(
            RightsRequest.objects.count(),
            0,
        )
        self.assertEqual(
            RequestStatusHistory
            .objects.count(),
            0,
        )

    def test_inactive_right_is_rejected(self):
        self.right.is_active = False
        self.right.save(
            update_fields=[
                "is_active"
            ]
        )

        with self.assertRaises(
            InactiveRightError
        ):
            (
                CaseWorkflowService
                .create_request(
                    data_subject=(
                        self.subject
                    ),
                    right=self.right,
                    request_details=(
                        "Prueba"
                    ),
                )
            )

        self.assertEqual(
            RightsRequest.objects.count(),
            0,
        )

    def test_missing_system_setting_is_rejected(self):
        SystemSetting.objects.all().delete()

        with self.assertRaises(
            CaseConfigurationError
        ):
            (
                CaseWorkflowService
                .create_request(
                    data_subject=(
                        self.subject
                    ),
                    right=self.right,
                    request_details=(
                        "Prueba"
                    ),
                )
            )

        self.assertEqual(
            RightsRequest.objects.count(),
            0,
        )

    def test_sequence_increments_between_requests(self):
        first = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Primera",
            )
        )

        second = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Segunda",
            )
        )

        first_seq = int(
            first.reference_number
            .rsplit("-", 1)[1]
        )
        second_seq = int(
            second.reference_number
            .rsplit("-", 1)[1]
        )

        self.assertEqual(
            second_seq,
            first_seq + 1,
        )
        self.assertNotEqual(
            first.reference_number,
            second.reference_number,
        )
