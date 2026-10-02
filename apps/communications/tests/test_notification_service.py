import base64
import uuid
from unittest.mock import patch

from django.core import mail
from django.test import (
    TestCase,
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
    CommunicationStateError,
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
    b"O" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"P" * 32
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
    EMAIL_BACKEND=(
        "django.core.mail.backends."
        "locmem.EmailBackend"
    ),
    DEFAULT_FROM_EMAIL=(
        "noreply@example.test"
    ),
    COMMUNICATION_MAX_ATTEMPTS=5,
    COMMUNICATION_RETRY_MINUTES=5,
)
class NotificationServiceTests(
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
                    "Solicitud de prueba"
                ),
            )
        )

    def queue(self, **kwargs):
        defaults = {
            "request": self.request,
            "communication_type": (
                "ACKNOWLEDGEMENT"
            ),
            "recipient": (
                "subject@example.com"
            ),
            "subject": (
                "Solicitud recibida"
            ),
            "body": (
                "Su solicitud fue recibida."
            ),
            "visible_to_subject": True,
        }
        defaults.update(kwargs)

        return (
            NotificationService
            .queue_email(**defaults)
        )

    def test_queue_encrypts_recipient_subject_and_body(self):
        communication = self.queue()

        self.assertEqual(
            communication.delivery_status,
            "PENDING",
        )

        self.assertNotIn(
            b"subject@example.com",
            bytes(
                communication
                .recipient_encrypted
            ),
        )
        self.assertNotIn(
            b"Solicitud recibida",
            bytes(
                communication
                .subject_encrypted
            ),
        )
        self.assertNotIn(
            b"Su solicitud fue recibida.",
            bytes(
                communication
                .body_encrypted
            ),
        )

    def test_decrypt_payload_roundtrip(self):
        communication = self.queue()

        payload = (
            NotificationService
            .decrypt_payload(
                communication
            )
        )

        self.assertEqual(
            payload["recipient"],
            "subject@example.com",
        )
        self.assertEqual(
            payload["subject"],
            "Solicitud recibida",
        )
        self.assertEqual(
            payload["body"],
            "Su solicitud fue recibida.",
        )

    def test_idempotency_key_prevents_duplicate_outbox_rows(self):
        key = uuid.uuid4()

        first = self.queue(
            idempotency_key=key
        )
        second = self.queue(
            idempotency_key=key
        )

        self.assertEqual(
            first.pk,
            second.pk,
        )

        self.assertEqual(
            RequestCommunication.objects
            .filter(
                idempotency_key=key
            )
            .count(),
            1,
        )

    def test_on_commit_callback_receives_only_uuid(self):
        captured = []

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            communication = self.queue(
                enqueue_callback=(
                    lambda value:
                    captured.append(value)
                )
            )

        self.assertEqual(
            captured,
            [communication.id],
        )

        self.assertIsInstance(
            captured[0],
            uuid.UUID,
        )

    def test_process_email_sends_and_marks_sent(self):
        communication = self.queue()

        result = (
            NotificationService
            .process_email(
                communication.id
            )
        )

        result.refresh_from_db()

        self.assertEqual(
            result.delivery_status,
            "SENT",
        )
        self.assertEqual(
            result.attempt_count,
            1,
        )
        self.assertIsNotNone(
            result.sent_at
        )
        self.assertIsNone(
            result.last_error
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

        self.assertEqual(
            mail.outbox[0].to,
            ["subject@example.com"],
        )
        self.assertEqual(
            mail.outbox[0].alternatives[0][1],
            "text/html",
        )
        self.assertIn(
            "Plataforma de Privacidad",
            mail.outbox[0].alternatives[0][0],
        )

    def test_sent_email_processing_is_idempotent(self):
        communication = self.queue()

        NotificationService.process_email(
            communication.id
        )

        NotificationService.process_email(
            communication.id
        )

        communication.refresh_from_db()

        self.assertEqual(
            communication.attempt_count,
            1,
        )
        self.assertEqual(
            len(mail.outbox),
            1,
        )

    def test_delivery_failure_sets_retry_state(self):
        communication = self.queue()

        with patch(
            "apps.communications.services.notifications."
            "EmailMultiAlternatives.send",
            side_effect=RuntimeError(
                "Simulated delivery failure"
            ),
        ):
            result = (
                NotificationService
                .process_email(
                    communication.id
                )
            )

        result.refresh_from_db()

        self.assertEqual(
            result.delivery_status,
            "FAILED",
        )
        self.assertEqual(
            result.attempt_count,
            1,
        )
        self.assertIsNotNone(
            result.next_retry_at
        )
        self.assertTrue(
            result.last_error
        )

    def test_retry_before_next_retry_at_is_rejected(self):
        communication = self.queue()

        communication.delivery_status = (
            "FAILED"
        )
        communication.next_retry_at = (
            NotificationService
            ._database_now()
            + NotificationService
            ._retry_delay(1)
        )
        communication.save(
            update_fields=[
                "delivery_status",
                "next_retry_at",
            ]
        )

        with self.assertRaises(
            CommunicationStateError
        ):
            (
                NotificationService
                .process_email(
                    communication.id
                )
            )

    def test_audit_does_not_store_email_subject_or_body(self):
        communication = self.queue()

        audit = AuditLog.objects.get(
            action=(
                "REQUEST_COMMUNICATION_QUEUED"
            ),
            entity_pk=str(
                communication.id
            ),
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
            "subject@example.com",
            serialized,
        )
        self.assertNotIn(
            "Solicitud recibida",
            serialized,
        )
        self.assertNotIn(
            "Su solicitud fue recibida.",
            serialized,
        )

    def test_visibility_is_explicitly_persisted(self):
        communication = self.queue(
            visible_to_subject=False
        )

        self.assertFalse(
            communication
            .visible_to_subject
        )
