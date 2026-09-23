import base64
from datetime import timedelta

from django.test import (
    TestCase,
    override_settings,
)
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.cases.models import (
    RequestAccessToken,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.cases.services.public_tracking import (
    PublicTrackingAccessError,
    PublicTrackingCodeResendService,
    PublicTrackingService,
)
from apps.cases.services.tokens import (
    RequestAccessTokenService,
)
from apps.legal_content.models import (
    RightCatalog,
)
from apps.organization.models import (
    SystemSetting,
)
from apps.communications.models import RequestCommunication
from apps.communications.services.notifications import NotificationService
from apps.subjects.services.subjects import (
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"Q" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"R" * 32
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
class PublicTrackingServiceTests(
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

        self.issued = (
            RequestAccessTokenService
            .issue(
                request=self.request,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .TRACKING
                ),
                ttl=timedelta(
                    hours=24
                ),
            )
        )

    def test_valid_reference_and_token_return_public_status(self):
        result = (
            PublicTrackingService
            .get_status(
                reference_number=(
                    self.request
                    .reference_number
                ),
                token=self.issued.token,
            )
        )

        self.assertEqual(
            result.reference_number,
            self.request.reference_number,
        )
        self.assertEqual(
            result.status,
            RightsRequest.Status.RECEIVED,
        )
        self.assertEqual(
            result.right_name,
            self.right.name,
        )
        self.assertEqual(
            len(result.history),
            1,
        )
        self.assertEqual(
            result.history[0].status,
            RightsRequest.Status.RECEIVED,
        )

    def test_reference_is_case_insensitive_and_trimmed(self):
        result = (
            PublicTrackingService
            .get_status(
                reference_number=(
                    "  "
                    + self.request
                    .reference_number
                    .lower()
                    + "  "
                ),
                token=self.issued.token,
            )
        )

        self.assertEqual(
            result.reference_number,
            self.request.reference_number,
        )

    def test_unknown_reference_returns_generic_access_error(self):
        with self.assertRaises(
            PublicTrackingAccessError
        ):
            (
                PublicTrackingService
                .get_status(
                    reference_number=(
                        "VINESA-2099-999999"
                    ),
                    token=self.issued.token,
                )
            )

    def test_invalid_token_returns_same_generic_access_error(self):
        with self.assertRaises(
            PublicTrackingAccessError
        ):
            (
                PublicTrackingService
                .get_status(
                    reference_number=(
                        self.request
                        .reference_number
                    ),
                    token="invalid-token",
                )
            )

    def test_token_for_another_request_is_rejected(self):
        other_subject = (
            SubjectService.create(
                subject_type="CUSTOMER",
                document_type="CEDULA",
                document_number=(
                    "1799999999"
                ),
                full_name="Otro Titular",
                email=(
                    "other@example.com"
                ),
            )
        )

        other_request = (
            CaseWorkflowService
            .create_request(
                data_subject=(
                    other_subject
                ),
                right=self.right,
                request_details=(
                    "Otra solicitud"
                ),
            )
        )

        with self.assertRaises(
            PublicTrackingAccessError
        ):
            (
                PublicTrackingService
                .get_status(
                    reference_number=(
                        other_request
                        .reference_number
                    ),
                    token=(
                        self.issued.token
                    ),
                )
            )

    def test_tracking_token_is_reusable_until_expiry_or_revocation(self):
        first = (
            PublicTrackingService
            .get_status(
                reference_number=(
                    self.request
                    .reference_number
                ),
                token=self.issued.token,
            )
        )

        second = (
            PublicTrackingService
            .get_status(
                reference_number=(
                    self.request
                    .reference_number
                ),
                token=self.issued.token,
            )
        )

        self.assertEqual(
            first.reference_number,
            second.reference_number,
        )

        self.issued.record \
            .refresh_from_db()

        self.assertIsNone(
            self.issued.record
            .revoked_at
        )

    def test_public_result_contains_no_subject_pii(self):
        result = (
            PublicTrackingService
            .get_status(
                reference_number=(
                    self.request
                    .reference_number
                ),
                token=self.issued.token,
            )
        )

        serialized = str(result)

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
            "Solicitud de prueba",
            serialized,
        )

    @override_settings(PUBLIC_TRACKING_RESEND_COOLDOWN_SECONDS=60)
    def test_matching_email_reissues_tracking_code_in_encrypted_outbox(self):
        RequestAccessToken.objects.filter(pk=self.issued.record.pk).update(
            created_at=timezone.now() - timedelta(minutes=2)
        )

        result = PublicTrackingCodeResendService.resend(
            reference_number=self.request.reference_number.lower(),
            email="SUBJECT@example.com",
        )

        self.assertTrue(result.queued)
        self.assertEqual(RequestCommunication.objects.count(), 1)
        communication = RequestCommunication.objects.get()
        payload = NotificationService.decrypt_payload(communication)
        self.assertEqual(payload["recipient"], "subject@example.com")
        self.assertIn(self.request.reference_number, payload["body"])
        self.assertIn("Código de seguimiento:", payload["body"])
        self.assertNotIn(
            self.request.reference_number.encode(),
            bytes(communication.body_encrypted),
        )
        self.issued.record.refresh_from_db()
        self.assertIsNotNone(self.issued.record.revoked_at)

    def test_wrong_email_does_not_reissue_or_queue_a_code(self):
        result = PublicTrackingCodeResendService.resend(
            reference_number=self.request.reference_number,
            email="wrong@example.com",
        )

        self.assertFalse(result.queued)
        self.assertEqual(RequestCommunication.objects.count(), 0)
        self.issued.record.refresh_from_db()
        self.assertIsNone(self.issued.record.revoked_at)

    def test_audit_does_not_store_token_or_subject_pii(self):
        (
            PublicTrackingService
            .get_status(
                reference_number=(
                    self.request
                    .reference_number
                ),
                token=self.issued.token,
            )
        )

        audit = AuditLog.objects.get(
            action=(
                "PUBLIC_TRACKING_ACCESSED"
            ),
            entity_pk=str(
                self.request.id
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
            self.issued.token,
            serialized,
        )
        self.assertNotIn(
            "subject@example.com",
            serialized,
        )
        self.assertNotIn(
            "Titular Prueba",
            serialized,
        )
