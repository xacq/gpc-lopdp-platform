import base64
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import (
    Role,
    UserRole,
)
from apps.audit.models import AuditLog
from apps.cases.models import (
    RequestClarification,
    RequestDeadline,
    RequestStatusHistory,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseAssigneeError,
    CaseConfigurationError,
    CasePermissionError,
    CaseTransitionError,
    CaseWorkflowService,
    InactiveRightError,
    RepresentativeSubjectMismatchError,
)
from apps.cases.services.deadlines import (
    ActiveDeadlineRequiredError,
    ClarificationLegalBasisError,
    DeadlineService,
)
from apps.legal_content.models import (
    RightCatalog,
    RightRule,
)
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

        self.rule = (
            RightRule.objects.create(
                right=self.right,
                response_days=5,
                day_count_type=(
                    RightRule
                    .DayCountType
                    .BUSINESS
                ),
                extension_allowed=True,
                extension_days=3,
                warning_days=2,
                clarification_effect=(
                    RightRule
                    .ClarificationEffect
                    .NO_CHANGE
                ),
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

    def create_user_with_role(
        self,
        *,
        email,
        role_code,
        is_active=True,
    ):
        user_model = get_user_model()

        user = user_model.objects.create_user(
            email=email,
            password="TestPassword123!",
            full_name="Usuario Prueba",
            is_active=is_active,
        )

        role, _ = Role.objects.get_or_create(
            code=role_code,
            defaults={
                "name": role_code,
                "is_active": True,
            },
        )

        UserRole.objects.create(
            user=user,
            role=role,
            is_primary=True,
        )

        return user

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

    def test_manager_can_assign_case_to_operator(self):
        manager = self.create_user_with_role(
            email="manager@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        operator = self.create_user_with_role(
            email="assigned@example.com",
            role_code=Role.Code.OPERADOR,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        result = CaseWorkflowService.assign(
            request=request,
            assignee=operator,
            actor=manager,
        )

        result.refresh_from_db()

        self.assertEqual(
            result.assigned_to_id,
            operator.id,
        )

        audit = AuditLog.objects.get(
            action="RIGHTS_REQUEST_ASSIGNED",
            entity_pk=str(request.id),
        )

        self.assertEqual(
            audit.new_values[
                "assigned_to_id"
            ],
            str(operator.id),
        )

    def test_operator_cannot_assign_case(self):
        operator = self.create_user_with_role(
            email="operator@example.com",
            role_code=Role.Code.OPERADOR,
        )

        another_operator = (
            self.create_user_with_role(
                email="other-operator@example.com",
                role_code=Role.Code.OPERADOR,
            )
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        with self.assertRaises(
            CasePermissionError
        ):
            CaseWorkflowService.assign(
                request=request,
                assignee=another_operator,
                actor=operator,
            )

        request.refresh_from_db()

        self.assertIsNone(
            request.assigned_to_id
        )

    def test_inactive_assignee_is_rejected(self):
        manager = self.create_user_with_role(
            email="manager@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        inactive_operator = (
            self.create_user_with_role(
                email="inactive@example.com",
                role_code=Role.Code.OPERADOR,
                is_active=False,
            )
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        with self.assertRaises(
            CaseAssigneeError
        ):
            CaseWorkflowService.assign(
                request=request,
                assignee=inactive_operator,
                actor=manager,
            )

        request.refresh_from_db()

        self.assertIsNone(
            request.assigned_to_id
        )

    def test_assigned_operator_can_start_review(self):
        manager = self.create_user_with_role(
            email="manager@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        operator = self.create_user_with_role(
            email="operator@example.com",
            role_code=Role.Code.OPERADOR,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        request = CaseWorkflowService.assign(
            request=request,
            assignee=operator,
            actor=manager,
        )

        result = (
            CaseWorkflowService.transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=operator,
            )
        )

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )

        history = (
            RequestStatusHistory.objects
            .filter(request=result)
            .order_by("id")
        )

        self.assertEqual(
            history.count(),
            2,
        )

        latest = history.last()

        self.assertEqual(
            latest.previous_status,
            RightsRequest
            .Status
            .RECEIVED,
        )
        self.assertEqual(
            latest.new_status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )
        self.assertEqual(
            latest.changed_by_id,
            operator.id,
        )

    def test_unassigned_operator_cannot_transition_case(self):
        operator = self.create_user_with_role(
            email="operator@example.com",
            role_code=Role.Code.OPERADOR,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        with self.assertRaises(
            CasePermissionError
        ):
            CaseWorkflowService.transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=operator,
            )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .RECEIVED,
        )

    def test_manager_can_transition_without_assignment(self):
        manager = self.create_user_with_role(
            email="manager@example.com",
            role_code=Role.Code.DPD,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        result = (
            CaseWorkflowService.transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=manager,
            )
        )

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )

    def test_invalid_operational_transition_is_rejected(self):
        manager = self.create_user_with_role(
            email="manager@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        with self.assertRaises(
            CaseTransitionError
        ):
            CaseWorkflowService.transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .RESPONDED
                ),
                actor=manager,
            )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .RECEIVED,
        )

        self.assertEqual(
            RequestStatusHistory.objects
            .filter(request=request)
            .count(),
            1,
        )

    def test_transition_generates_audit_entry(self):
        manager = self.create_user_with_role(
            email="manager@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        CaseWorkflowService.transition(
            request=request,
            target_status=(
                RightsRequest
                .Status
                .UNDER_REVIEW
            ),
            actor=manager,
        )

        audit = AuditLog.objects.get(
            action=(
                "RIGHTS_REQUEST_STATUS_CHANGED"
            ),
            entity_pk=str(request.id),
        )

        self.assertEqual(
            audit.previous_values["status"],
            RightsRequest.Status.RECEIVED,
        )
        self.assertEqual(
            audit.new_values["status"],
            RightsRequest.Status.UNDER_REVIEW,
        )

    def test_direct_awaiting_information_transition_is_rejected(self):
        manager = self.create_user_with_role(
            email="manager-direct@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=manager,
            )
        )

        with self.assertRaises(
            CaseTransitionError
        ):
            CaseWorkflowService.transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .AWAITING_INFORMATION
                ),
                actor=manager,
            )

    def test_request_clarification_moves_case_to_awaiting_information(self):
        manager = self.create_user_with_role(
            email="manager-clarify@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=manager,
            )
        )

        clarification = (
            CaseWorkflowService
            .request_clarification(
                request=request,
                message=(
                    "Complete la información."
                ),
                actor=manager,
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .AWAITING_INFORMATION,
        )

        self.assertEqual(
            clarification.status,
            RequestClarification
            .Status
            .REQUESTED,
        )

        clarification_history = (
            RequestStatusHistory.objects
            .filter(
                request=request,
                previous_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                new_status=(
                    RightsRequest
                    .Status
                    .AWAITING_INFORMATION
                ),
            )
        )

        self.assertEqual(
            clarification_history.count(),
            1,
        )

        history = (
            clarification_history.first()
        )

        self.assertEqual(
            history.changed_by_id,
            manager.id,
        )

    def test_receive_clarification_returns_case_to_under_review(self):
        manager = self.create_user_with_role(
            email="manager-receive@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=manager,
            )
        )

        clarification = (
            CaseWorkflowService
            .request_clarification(
                request=request,
                message="Aclare.",
                actor=manager,
            )
        )

        received = (
            CaseWorkflowService
            .receive_clarification(
                clarification=clarification,
                response_message=(
                    "Información aclarada."
                ),
                actor=manager,
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            received.status,
            RequestClarification
            .Status
            .RECEIVED,
        )

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )

    def test_assigned_operator_can_manage_clarification(self):
        manager = self.create_user_with_role(
            email="manager-operator@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        operator = self.create_user_with_role(
            email="operator-clarify@example.com",
            role_code=Role.Code.OPERADOR,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        request = CaseWorkflowService.assign(
            request=request,
            assignee=operator,
            actor=manager,
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=operator,
            )
        )

        clarification = (
            CaseWorkflowService
            .request_clarification(
                request=request,
                message="Aclare.",
                actor=operator,
            )
        )

        CaseWorkflowService.receive_clarification(
            clarification=clarification,
            response_message="Respuesta.",
            actor=operator,
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )

    def test_manager_extension_moves_under_review_to_extended(self):
        manager = self.create_user_with_role(
            email="manager-extension@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=manager,
            )
        )

        extension = (
            CaseWorkflowService
            .apply_extension(
                request=request,
                reason=(
                    "Complejidad del caso"
                ),
                actor=manager,
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .EXTENDED,
        )

        self.assertTrue(
            request.extension_applied
        )

        self.assertEqual(
            extension.deadline_type,
            RequestDeadline
            .DeadlineType
            .EXTENSION,
        )

        self.assertEqual(
            request.current_due_at,
            extension.due_at,
        )

    def test_operator_cannot_apply_extension(self):
        manager = self.create_user_with_role(
            email="manager-op-extension@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        operator = self.create_user_with_role(
            email="operator-extension@example.com",
            role_code=Role.Code.OPERADOR,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        request = CaseWorkflowService.assign(
            request=request,
            assignee=operator,
            actor=manager,
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=operator,
            )
        )

        with self.assertRaises(
            CasePermissionError
        ):
            CaseWorkflowService.apply_extension(
                request=request,
                reason="No autorizado",
                actor=operator,
            )

        request.refresh_from_db()

        self.assertFalse(
            request.extension_applied
        )

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )

    def test_extended_case_returns_to_extended_after_clarification(self):
        manager = self.create_user_with_role(
            email="manager-extended-clarify@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=manager,
            )
        )

        CaseWorkflowService.apply_extension(
            request=request,
            reason="Extensión válida",
            actor=manager,
        )

        request.refresh_from_db()

        clarification = (
            CaseWorkflowService
            .request_clarification(
                request=request,
                message="Aclare.",
                actor=manager,
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .AWAITING_INFORMATION,
        )

        CaseWorkflowService.receive_clarification(
            clarification=clarification,
            response_message="Respuesta.",
            actor=manager,
        )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .EXTENDED,
        )

    def test_extension_failure_rolls_back_case_status(self):
        manager = self.create_user_with_role(
            email="manager-extension-failure@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=manager,
            )
        )

        with self.assertRaises(
            ActiveDeadlineRequiredError
        ):
            CaseWorkflowService.apply_extension(
                request=request,
                reason="Sin plazo inicial",
                actor=manager,
            )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )
        self.assertFalse(
            request.extension_applied
        )

    def test_clarification_failure_does_not_change_case_status(self):
        manager = self.create_user_with_role(
            email="manager-clarify-failure@example.com",
            role_code=Role.Code.RESPONSABLE,
        )

        self.rule.clarification_effect = (
            RightRule
            .ClarificationEffect
            .PAUSE
        )
        self.rule.save(
            update_fields=[
                "clarification_effect",
            ]
        )

        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        request = (
            CaseWorkflowService
            .transition(
                request=request,
                target_status=(
                    RightsRequest
                    .Status
                    .UNDER_REVIEW
                ),
                actor=manager,
            )
        )

        with self.assertRaises(
            ClarificationLegalBasisError
        ):
            (
                CaseWorkflowService
                .request_clarification(
                    request=request,
                    message="Aclare.",
                    actor=manager,
                )
            )

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            RightsRequest
            .Status
            .UNDER_REVIEW,
        )

        self.assertEqual(
            RequestClarification.objects
            .filter(request=request)
            .count(),
            0,
        )

