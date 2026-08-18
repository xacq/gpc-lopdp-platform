import base64
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import (
    TestCase,
    override_settings,
)

from apps.accounts.models import (
    Role,
    UserRole,
)
from apps.audit.models import AuditLog
from apps.cases.models import (
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.legal_content.models import (
    RightCatalog,
)
from apps.organization.models import (
    SystemSetting,
)
from apps.retention.models import (
    DataDisposalEvent,
    RetentionRule,
)
from apps.retention.services.retention import (
    RetentionEventStateError,
    RetentionPermissionError,
    RetentionService,
)
from apps.subjects.services.subjects import (
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"W" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"X" * 32
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
class RetentionServiceTests(TestCase):

    def setUp(self):
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
                document_number=(
                    "1712345678"
                ),
                full_name=(
                    "Titular Prueba"
                ),
                email=(
                    "subject@example.com"
                ),
            )
        )

        self.request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details=(
                    "Solicitud reservada"
                ),
            )
        )

        self.rule = (
            RetentionRule.objects.create(
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                retention_days=30,
                retention_anchor=(
                    RetentionRule
                    .RetentionAnchor
                    .CLOSED_AT
                ),
                final_action=(
                    RetentionRule
                    .FinalAction
                    .ARCHIVE
                ),
                requires_approval=True,
                legal_basis=(
                    "Regla de prueba"
                ),
                is_active=True,
            )
        )

        self.manager = (
            self.create_user_with_role(
                email=(
                    "manager@example.com"
                ),
                role_code=(
                    Role.Code.RESPONSABLE
                ),
            )
        )

        self.operator = (
            self.create_user_with_role(
                email=(
                    "operator@example.com"
                ),
                role_code=(
                    Role.Code.OPERADOR
                ),
            )
        )

    def create_user_with_role(
        self,
        *,
        email,
        role_code,
    ):
        user_model = get_user_model()

        user = user_model.objects.create_user(
            email=email,
            password="TestPassword123!",
            full_name="Usuario Prueba",
            is_active=True,
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

    def close_at_days_ago(
        self,
        days: int,
    ):
        now = (
            RetentionService
            ._database_now()
        )

        closed_at = (
            now
            - timedelta(days=days)
        )

        received_at = (
            closed_at
            - timedelta(days=1)
        )

        created_at = (
            received_at
            - timedelta(minutes=1)
        )

        RightsRequest.objects \
            .filter(
                pk=self.request.pk
            ) \
            .update(
                created_at=created_at,
                received_at=received_at,
                closed_at=closed_at,
            )

        self.request.refresh_from_db()

    def test_open_request_is_not_eligible_for_closed_anchor(self):
        result = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        self.assertIsNone(result)

        self.assertEqual(
            DataDisposalEvent.objects.count(),
            0,
        )

    def test_request_before_retention_period_is_not_due(self):
        self.close_at_days_ago(10)

        result = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        self.assertIsNone(result)

    def test_due_request_creates_pending_approval_event(self):
        self.close_at_days_ago(31)

        event = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .PENDING_APPROVAL,
        )

        self.assertEqual(
            event.action,
            RetentionRule
            .FinalAction
            .ARCHIVE,
        )

        self.assertEqual(
            event.entity_pk,
            str(self.request.id),
        )

    def test_detection_is_idempotent_for_open_event(self):
        self.close_at_days_ago(31)

        first = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        second = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        self.assertEqual(
            first.pk,
            second.pk,
        )

        self.assertEqual(
            DataDisposalEvent.objects.count(),
            1,
        )

    def test_rule_without_approval_creates_approved_event(self):
        self.rule.requires_approval = False
        self.rule.save(
            update_fields=[
                "requires_approval",
            ]
        )

        self.close_at_days_ago(31)

        event = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .APPROVED,
        )

        self.assertIsNotNone(
            event.approved_at
        )

    def test_manager_can_approve_pending_event(self):
        self.close_at_days_ago(31)

        event = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        event = (
            RetentionService.approve(
                event=event,
                actor=self.manager,
            )
        )

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .APPROVED,
        )

        self.assertEqual(
            event.approved_by_id,
            self.manager.id,
        )

        self.assertIsNotNone(
            event.approved_at
        )

    def test_operator_cannot_approve_retention_event(self):
        self.close_at_days_ago(31)

        event = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        with self.assertRaises(
            RetentionPermissionError
        ):
            RetentionService.approve(
                event=event,
                actor=self.operator,
            )

        event.refresh_from_db()

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .PENDING_APPROVAL,
        )

    def test_approved_event_cannot_be_approved_twice(self):
        self.close_at_days_ago(31)

        event = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        event = (
            RetentionService.approve(
                event=event,
                actor=self.manager,
            )
        )

        with self.assertRaises(
            RetentionEventStateError
        ):
            RetentionService.approve(
                event=event,
                actor=self.manager,
            )

    def test_audit_contains_no_subject_pii(self):
        self.close_at_days_ago(31)

        event = (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

        audit = AuditLog.objects.get(
            action=(
                "DATA_DISPOSAL_EVENT_DETECTED"
            ),
            entity_pk=str(event.id),
        )

        serialized = str(
            {
                "metadata": (
                    audit.metadata
                ),
                "description": (
                    audit.description
                ),
            }
        )

        self.assertNotIn(
            "Titular Prueba",
            serialized,
        )
        self.assertNotIn(
            "subject@example.com",
            serialized,
        )
        self.assertNotIn(
            "1712345678",
            serialized,
        )
        self.assertNotIn(
            "Solicitud reservada",
            serialized,
        )
