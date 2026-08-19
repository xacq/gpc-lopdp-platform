import base64
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cases.models import RequestDeadline
from apps.cases.services.cases import CaseWorkflowService
from apps.communications.models import RequestCommunication
from apps.communications.services.deadline_alerts import DeadlineAlertService
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.services.subjects import SubjectService


ENCRYPTION_KEY = base64.b64encode(b"M" * 32).decode("ascii")
LOOKUP_KEY = base64.b64encode(b"N" * 32).decode("ascii")


@override_settings(
    PII_ENCRYPTION_ACTIVE_VERSION=1,
    PII_ENCRYPTION_KEYS={1: ENCRYPTION_KEY},
    LOOKUP_HMAC_ACTIVE_VERSION=1,
    LOOKUP_HMAC_KEYS={1: LOOKUP_KEY},
)
class DeadlineAlertServiceTests(TestCase):
    def setUp(self):
        self.settings = SystemSetting.objects.create(
            legal_name="VINESA S.A.",
            trade_name="VINESA",
            ruc="1792049598001",
            domain="privacidad.vinesa.test",
            contact_email="contacto@example.test",
            dpd_email="dpd@example.test",
            request_prefix="VS",
            timezone="America/Guayaquil",
        )
        right = RightCatalog.objects.create(code="ACCESS", name="Acceso")
        subject = SubjectService.create(
            subject_type="CUSTOMER",
            document_type="CEDULA",
            document_number="1712345678",
            full_name="Titular Alerta",
            email="titular@example.test",
        )
        self.request = CaseWorkflowService.create_request(
            data_subject=subject,
            right=right,
            request_details="Solicitud de prueba",
        )

    def create_deadline(self, *, warning_at, due_at, status="ACTIVE"):
        return RequestDeadline.objects.create(
            request=self.request,
            deadline_type=RequestDeadline.DeadlineType.INITIAL,
            sequence_number=1,
            starts_at=warning_at - timedelta(days=1),
            warning_at=warning_at,
            due_at=due_at,
            status=status,
            rule_snapshot={},
        )

    def test_queues_due_alert_and_marks_warning(self):
        now = timezone.now()
        deadline = self.create_deadline(
            warning_at=now - timedelta(minutes=1),
            due_at=now + timedelta(days=2),
        )
        result = DeadlineAlertService.queue_due_alerts(now=now)
        self.assertEqual(result.queued, 1)
        deadline.refresh_from_db()
        self.assertEqual(deadline.warning_sent_at, now)
        communication = RequestCommunication.objects.get(
            communication_type="DEADLINE_ALERT"
        )
        self.assertFalse(communication.visible_to_subject)

    def test_repeated_batch_is_idempotent(self):
        now = timezone.now()
        self.create_deadline(
            warning_at=now - timedelta(minutes=1),
            due_at=now + timedelta(days=1),
        )
        first = DeadlineAlertService.queue_due_alerts(now=now)
        second = DeadlineAlertService.queue_due_alerts(now=now)
        self.assertEqual(first.queued, 1)
        self.assertEqual(second.queued, 0)
        self.assertEqual(
            RequestCommunication.objects.filter(
                communication_type="DEADLINE_ALERT"
            ).count(),
            1,
        )

    def test_ignores_future_warning_and_expired_deadline(self):
        now = timezone.now()
        self.create_deadline(
            warning_at=now + timedelta(hours=1),
            due_at=now + timedelta(days=1),
        )
        result = DeadlineAlertService.queue_due_alerts(now=now)
        self.assertEqual(result.queued, 0)
