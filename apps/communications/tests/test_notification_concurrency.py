import base64
import threading
import uuid
from unittest.mock import patch

from django.db import close_old_connections
from django.test import (
    TransactionTestCase,
    override_settings,
)

from apps.audit.models import AuditLog
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.communications.models import (
    RequestCommunication,
)
from apps.communications.services.notifications import (
    NotificationService,
)
from apps.legal_content.models import (
    RightCatalog,
)
from apps.organization.models import (
    SystemSetting,
)
from apps.subjects.services.subjects import (
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"Y" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"Z" * 32
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
class NotificationConcurrencyTests(
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

        right = RightCatalog.objects.create(
            code="TEST_RIGHT",
            name="Derecho de prueba",
            is_active=True,
        )

        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Prueba",
            email="subject@example.com",
        )

        self.request = (
            CaseWorkflowService
            .create_request(
                data_subject=subject,
                right=right,
                request_details=(
                    "Solicitud de prueba"
                ),
            )
        )

    def _queue(
        self,
        *,
        key,
        barrier,
        results,
        errors,
    ):
        close_old_connections()

        try:
            barrier.wait(timeout=10)

            communication = (
                NotificationService
                .queue_email(
                    request=self.request,
                    communication_type=(
                        "ACKNOWLEDGEMENT"
                    ),
                    recipient=(
                        "subject@example.com"
                    ),
                    subject=(
                        "Solicitud recibida"
                    ),
                    body=(
                        "Su solicitud fue "
                        "recibida."
                    ),
                    visible_to_subject=True,
                    idempotency_key=key,
                )
            )

            results.append(
                communication.id
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    def test_concurrent_same_idempotency_key_creates_one_row(self):
        workers = 8
        key = uuid.uuid4()
        barrier = threading.Barrier(
            workers
        )
        results = []
        errors = []

        threads = [
            threading.Thread(
                target=self._queue,
                kwargs={
                    "key": key,
                    "barrier": barrier,
                    "results": results,
                    "errors": errors,
                },
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

        rows = (
            RequestCommunication.objects
            .filter(
                idempotency_key=key
            )
        )

        self.assertEqual(
            rows.count(),
            1,
        )

        communication = rows.get()

        self.assertEqual(
            communication.id,
            results[0],
        )

        self.assertEqual(
            AuditLog.objects
            .filter(
                action=(
                    "REQUEST_COMMUNICATION_QUEUED"
                ),
                entity_pk=str(
                    communication.id
                ),
            )
            .count(),
            1,
        )

    def test_concurrent_processing_sends_email_only_once(self):
        communication = (
            NotificationService
            .queue_email(
                request=self.request,
                communication_type=(
                    "ACKNOWLEDGEMENT"
                ),
                recipient=(
                    "subject@example.com"
                ),
                subject=(
                    "Solicitud recibida"
                ),
                body=(
                    "Su solicitud fue recibida."
                ),
                visible_to_subject=True,
                idempotency_key=(
                    uuid.uuid4()
                ),
            )
        )

        send_started = threading.Event()
        release_send = threading.Event()
        send_counter_lock = threading.Lock()
        send_counter = {
            "count": 0,
        }
        results = []
        errors = []

        def fake_send(
            _message,
            *,
            fail_silently=False,
        ):
            with send_counter_lock:
                send_counter["count"] += 1

            send_started.set()

            if not release_send.wait(
                timeout=10
            ):
                raise RuntimeError(
                    "Test send release timed out."
                )

            return 1

        def process():
            close_old_connections()

            try:
                result = (
                    NotificationService
                    .process_email(
                        communication.id
                    )
                )
                results.append(
                    result.delivery_status
                )
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        with patch(
            "apps.communications.services."
            "notifications.EmailMessage.send",
            new=fake_send,
        ):
            first = threading.Thread(
                target=process
            )
            first.start()

            self.assertTrue(
                send_started.wait(
                    timeout=10
                )
            )

            second = threading.Thread(
                target=process
            )
            second.start()

            second.join(
                timeout=10
            )

            self.assertFalse(
                second.is_alive()
            )

            release_send.set()

            first.join(
                timeout=10
            )

        self.assertFalse(
            first.is_alive()
        )

        self.assertEqual(
            errors,
            [],
        )

        communication.refresh_from_db()

        self.assertEqual(
            communication.delivery_status,
            "SENT",
        )

        self.assertEqual(
            communication.attempt_count,
            1,
        )

        self.assertEqual(
            send_counter["count"],
            1,
        )

        self.assertEqual(
            RequestCommunication.objects
            .filter(
                pk=communication.id
            )
            .count(),
            1,
        )

        self.assertEqual(
            AuditLog.objects
            .filter(
                action=(
                    "REQUEST_COMMUNICATION_SENT"
                ),
                entity_pk=str(
                    communication.id
                ),
            )
            .count(),
            1,
        )

