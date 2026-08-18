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
from apps.cases.models import RightsRequest
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
    b"A" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"B" * 32
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
class RetentionExecutionTests(
    TestCase
):

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

    def pending_event(self):
        self.close_at_days_ago(31)

        return (
            RetentionService
            .detect_rights_request(
                request=self.request
            )
        )

    def approved_event(self):
        event = self.pending_event()

        return (
            RetentionService.approve(
                event=event,
                actor=self.manager,
            )
        )

    def test_pending_event_cannot_execute(self):
        event = self.pending_event()
        calls = []

        with self.assertRaises(
            RetentionEventStateError
        ):
            RetentionService.execute(
                event=event,
                actor=self.manager,
                executor=lambda **kwargs: (
                    calls.append(kwargs)
                ),
            )

        self.assertEqual(
            calls,
            [],
        )

    def test_approved_event_executes_and_records_evidence(self):
        event = self.approved_event()
        calls = []

        event = (
            RetentionService.execute(
                event=event,
                actor=self.manager,
                executor=lambda **kwargs: (
                    calls.append(kwargs)
                ),
            )
        )

        self.assertEqual(
            len(calls),
            1,
        )

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .EXECUTED,
        )

        self.assertEqual(
            event.executed_by_id,
            self.manager.id,
        )

        self.assertIsNotNone(
            event.executed_at
        )

        self.assertEqual(
            len(event.evidence_sha256),
            64,
        )

        int(
            event.evidence_sha256,
            16,
        )

    def test_operator_cannot_execute_retention_event(self):
        event = self.approved_event()

        with self.assertRaises(
            RetentionPermissionError
        ):
            RetentionService.execute(
                event=event,
                actor=self.operator,
                executor=lambda **kwargs: None,
            )

        event.refresh_from_db()

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .APPROVED,
        )

    def test_executor_failure_is_sanitized_and_persisted(self):
        event = self.approved_event()

        def failing_executor(**kwargs):
            raise RuntimeError(
                "subject@example.com "
                "1712345678"
            )

        event = (
            RetentionService.execute(
                event=event,
                actor=self.manager,
                executor=failing_executor,
            )
        )

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .FAILED,
        )

        self.assertEqual(
            event.error_code,
            "RETENTION_EXECUTION_FAILED",
        )

        self.assertEqual(
            event.error_message,
            "RuntimeError",
        )

        self.assertNotIn(
            "subject@example.com",
            event.error_message,
        )

        self.assertNotIn(
            "1712345678",
            event.error_message,
        )

        self.assertIsNone(
            event.executed_at
        )

        self.assertIsNone(
            event.evidence_sha256
        )

    def test_failed_event_can_be_reset_for_retry(self):
        event = self.approved_event()

        event = (
            RetentionService.execute(
                event=event,
                actor=self.manager,
                executor=lambda **kwargs: (
                    (_ for _ in ())
                    .throw(
                        ValueError(
                            "sensitive detail"
                        )
                    )
                ),
            )
        )

        event = (
            RetentionService
            .retry_failed(
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

        self.assertIsNone(
            event.error_code
        )

        self.assertIsNone(
            event.error_message
        )

    def test_failed_event_can_be_successfully_retried(self):
        event = self.approved_event()

        event = (
            RetentionService.execute(
                event=event,
                actor=self.manager,
                executor=lambda **kwargs: (
                    (_ for _ in ())
                    .throw(
                        RuntimeError(
                            "first attempt"
                        )
                    )
                ),
            )
        )

        event = (
            RetentionService
            .retry_failed(
                event=event,
                actor=self.manager,
            )
        )

        calls = []

        event = (
            RetentionService.execute(
                event=event,
                actor=self.manager,
                executor=lambda **kwargs: (
                    calls.append(kwargs)
                ),
            )
        )

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .EXECUTED,
        )

        self.assertEqual(
            len(calls),
            1,
        )

    def test_execution_audit_contains_no_subject_pii(self):
        event = self.approved_event()

        event = (
            RetentionService.execute(
                event=event,
                actor=self.manager,
                executor=lambda **kwargs: None,
            )
        )

        audit = AuditLog.objects.get(
            action=(
                "DATA_DISPOSAL_EVENT_EXECUTED"
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
