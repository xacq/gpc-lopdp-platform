import base64
from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.cases.services.cases import CaseWorkflowService
from apps.communications.models import RequestCommunication
from apps.communications.services.notifications import NotificationService
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService


ENCRYPTION_KEY = base64.b64encode(b"A" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"B" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.test",
    COMMUNICATION_MAX_ATTEMPTS=5,
    COMMUNICATION_RETRY_MINUTES=5,
)
class OutboxDispatchTests(TestCase):
    def setUp(self):
        SystemSetting.objects.create(
            legal_name="VINOS Y ESPIRITUOSOS VINESA S.A.",
            trade_name="VINESA",
            ruc="1792049598001",
            domain="privacidad.vinesa.test",
            contact_email="privacidad@vinesa.com.ec",
            request_prefix="VINESA",
            timezone="America/Guayaquil",
        )
        right = RightCatalog.objects.create(
            code="OUTBOX_TEST",
            name="Derecho outbox",
            is_active=True,
        )
        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Outbox",
            email="outbox-subject@example.com",
        )
        self.case = CaseWorkflowService.create_request(
            data_subject=subject,
            right=right,
            request_details="Solicitud para probar outbox",
        )

    def queue(self, index=1):
        return NotificationService.queue_email(
            request=self.case,
            communication_type="ACKNOWLEDGEMENT",
            recipient=f"private-{index}@example.com",
            subject=f"Asunto confidencial {index}",
            body=f"Contenido confidencial {index}",
            visible_to_subject=False,
        )

    def test_batch_sends_pending_messages_and_audits_command_source(self):
        first = self.queue(1)
        second = self.queue(2)

        result = NotificationService.process_due_email_batch(batch_size=10)

        self.assertEqual(result.selected, 2)
        self.assertEqual(result.sent, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(len(mail.outbox), 2)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.delivery_status, "SENT")
        self.assertEqual(second.delivery_status, "SENT")
        self.assertEqual(
            AuditLog.objects.filter(
                action="REQUEST_COMMUNICATION_SENT",
                source=AuditLog.Source.COMMAND,
            ).count(),
            2,
        )

    def test_batch_size_limits_processing_in_queue_order(self):
        first = self.queue(1)
        second = self.queue(2)
        third = self.queue(3)
        now = NotificationService._database_now()
        RequestCommunication.objects.filter(pk=first.pk).update(
            queued_at=now - timedelta(seconds=3)
        )
        RequestCommunication.objects.filter(pk=second.pk).update(
            queued_at=now - timedelta(seconds=2)
        )
        RequestCommunication.objects.filter(pk=third.pk).update(
            queued_at=now - timedelta(seconds=1)
        )

        result = NotificationService.process_due_email_batch(batch_size=2)

        self.assertEqual(result.selected, 2)
        first.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(first.delivery_status, "SENT")
        self.assertEqual(second.delivery_status, "SENT")
        self.assertEqual(third.delivery_status, "PENDING")

    def test_future_retry_and_exhausted_failure_are_not_selected(self):
        future_retry = self.queue(1)
        exhausted = self.queue(2)
        now = NotificationService._database_now()
        RequestCommunication.objects.filter(pk=future_retry.pk).update(
            delivery_status="FAILED",
            attempt_count=1,
            next_retry_at=now + timedelta(minutes=5),
        )
        RequestCommunication.objects.filter(pk=exhausted.pk).update(
            delivery_status="FAILED",
            attempt_count=5,
            next_retry_at=now - timedelta(minutes=1),
        )

        result = NotificationService.process_due_email_batch(batch_size=10)

        self.assertEqual(result.selected, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_due_failed_message_is_retried(self):
        communication = self.queue()
        RequestCommunication.objects.filter(pk=communication.pk).update(
            delivery_status="FAILED",
            attempt_count=1,
            next_retry_at=(
                NotificationService._database_now() - timedelta(minutes=1)
            ),
        )

        result = NotificationService.process_due_email_batch(batch_size=10)

        self.assertEqual(result.selected, 1)
        self.assertEqual(result.sent, 1)
        communication.refresh_from_db()
        self.assertEqual(communication.attempt_count, 2)
        self.assertEqual(communication.delivery_status, "SENT")

    def test_drain_command_processes_all_batches_with_safe_output(self):
        for index in range(1, 6):
            self.queue(index)
        output = StringIO()

        call_command(
            "process_email_outbox",
            batch_size=2,
            drain=True,
            stdout=output,
            no_color=True,
        )

        rendered = output.getvalue()
        self.assertEqual(
            RequestCommunication.objects.filter(delivery_status="SENT").count(),
            5,
        )
        self.assertIn("seleccionados=5", rendered)
        self.assertIn("enviados=5", rendered)
        for forbidden in (
            "private-1@example.com",
            "Asunto confidencial",
            "Contenido confidencial",
            str(self.case.id),
            self.case.reference_number,
        ):
            self.assertNotIn(forbidden, rendered)

    def test_invalid_batch_size_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command("process_email_outbox", batch_size=0)

        with self.assertRaises(ValueError):
            NotificationService.process_due_email_batch(batch_size=1001)
