import base64
import threading
import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import (
    TransactionTestCase,
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
    RetentionService,
)
from apps.subjects.services.subjects import (
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
class RetentionConcurrencyTests(
    TransactionTestCase
):
    reset_sequences = True

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
                document_number="1712345678",
                full_name="Titular Prueba",
                email="subject@example.com",
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
                entity_type="RIGHTS_REQUEST",
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
                legal_basis="Regla de prueba",
                is_active=True,
            )
        )

        user_model = get_user_model()

        self.manager = (
            user_model.objects.create_user(
                email="manager@example.com",
                password="TestPassword123!",
                full_name="Responsable",
                is_active=True,
            )
        )

        role, _ = Role.objects.get_or_create(
            code=Role.Code.RESPONSABLE,
            defaults={
                "name": "Responsable",
                "is_active": True,
            },
        )

        UserRole.objects.create(
            user=self.manager,
            role=role,
            is_primary=True,
        )

        self._close_at_days_ago(31)

    def _close_at_days_ago(
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

    def test_concurrent_detection_creates_one_open_event(self):
        workers = 6
        barrier = threading.Barrier(
            workers
        )
        results = []
        errors = []
        result_lock = threading.Lock()

        def detect():
            close_old_connections()

            try:
                barrier.wait(timeout=10)

                request = (
                    RightsRequest.objects
                    .get(pk=self.request.pk)
                )

                event = (
                    RetentionService
                    .detect_rights_request(
                        request=request
                    )
                )

                with result_lock:
                    results.append(
                        event.id
                    )
            except Exception as exc:
                with result_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(
                target=detect
            )
            for _ in range(workers)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(
            any(
                thread.is_alive()
                for thread in threads
            )
        )

        self.assertEqual(
            errors,
            [],
        )

        self.assertEqual(
            len(results),
            workers,
        )

        self.assertEqual(
            len(set(results)),
            1,
        )

        events = (
            DataDisposalEvent.objects
            .filter(
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                entity_pk=str(
                    self.request.id
                ),
                action=(
                    RetentionRule
                    .FinalAction
                    .ARCHIVE
                ),
            )
        )

        self.assertEqual(
            events.count(),
            1,
        )

        self.assertEqual(
            AuditLog.objects
            .filter(
                action=(
                    "DATA_DISPOSAL_EVENT_DETECTED"
                ),
                entity_pk=str(
                    events.get().id
                ),
            )
            .count(),
            1,
        )

    def test_concurrent_execution_calls_executor_once(self):
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

        first_started = threading.Event()
        release_first = threading.Event()
        executor_lock = threading.Lock()
        executor_calls = {
            "count": 0,
        }
        results = []
        errors = []
        result_lock = threading.Lock()

        def executor(**kwargs):
            with executor_lock:
                executor_calls["count"] += 1
                call_number = (
                    executor_calls["count"]
                )

            if call_number == 1:
                first_started.set()

                if not release_first.wait(
                    timeout=10
                ):
                    raise RuntimeError(
                        "Executor release timeout."
                    )

        def execute():
            close_old_connections()

            try:
                local_event = (
                    DataDisposalEvent.objects
                    .get(pk=event.pk)
                )

                manager = (
                    get_user_model()
                    .objects.get(
                        pk=self.manager.pk
                    )
                )

                result = (
                    RetentionService.execute(
                        event=local_event,
                        actor=manager,
                        executor=executor,
                    )
                )

                with result_lock:
                    results.append(
                        result.status
                    )
            except Exception as exc:
                with result_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        first = threading.Thread(
            target=execute
        )
        first.start()

        self.assertTrue(
            first_started.wait(
                timeout=10
            )
        )

        second = threading.Thread(
            target=execute
        )
        second.start()

        time.sleep(0.25)
        release_first.set()

        first.join(timeout=20)
        second.join(timeout=20)

        self.assertFalse(
            first.is_alive()
        )

        self.assertFalse(
            second.is_alive()
        )

        self.assertEqual(
            errors,
            [],
        )

        self.assertEqual(
            len(results),
            2,
        )

        self.assertEqual(
            results.count(
                DataDisposalEvent
                .Status
                .EXECUTED
            ),
            2,
        )

        self.assertEqual(
            executor_calls["count"],
            1,
        )

        event.refresh_from_db()

        self.assertEqual(
            event.status,
            DataDisposalEvent
            .Status
            .EXECUTED,
        )

        self.assertEqual(
            AuditLog.objects
            .filter(
                action=(
                    "DATA_DISPOSAL_EVENT_EXECUTED"
                ),
                entity_pk=str(event.id),
            )
            .count(),
            1,
        )
