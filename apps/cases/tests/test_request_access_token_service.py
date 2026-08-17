import base64
from datetime import timedelta
from unittest.mock import patch
import uuid

from django.test import (
    TestCase,
    override_settings,
)

from apps.audit.models import AuditLog
from apps.cases.models import (
    RequestAccessToken,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.cases.services.tokens import (
    RequestAccessTokenService,
    TokenBindingError,
    TokenInvalidOrExpiredError,
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
    b"K" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"L" * 32
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
    ACCESS_TOKEN_MAX_FAILED_ATTEMPTS=5,
    ACCESS_TOKEN_LOCK_MINUTES=15,
)
class RequestAccessTokenServiceTests(
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

    def issue_tracking(self):
        return (
            RequestAccessTokenService
            .issue(
                request=self.request,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .TRACKING
                ),
                ttl=timedelta(
                    hours=1
                ),
            )
        )

    def test_issue_returns_plain_token_once_and_stores_only_hash(self):
        issued = self.issue_tracking()

        record = issued.record
        raw = issued.token

        self.assertTrue(raw)

        self.assertEqual(
            len(record.token_hash),
            64,
        )

        self.assertNotEqual(
            record.token_hash,
            raw,
        )

        database_text = (
            RequestAccessToken.objects
            .get(pk=record.pk)
            .token_hash
        )

        self.assertNotIn(
            raw,
            database_text,
        )

    def test_issue_uses_active_lookup_key_version(self):
        issued = self.issue_tracking()

        self.assertEqual(
            issued.record
            .lookup_key_version,
            1,
        )

    def test_tracking_token_has_no_resource_binding(self):
        issued = self.issue_tracking()

        self.assertIsNone(
            issued.record.resource_type
        )
        self.assertIsNone(
            issued.record.resource_id
        )

    def test_file_download_requires_attachment_binding(self):
        with self.assertRaises(
            TokenBindingError
        ):
            (
                RequestAccessTokenService
                .issue(
                    request=self.request,
                    purpose=(
                        RequestAccessToken
                        .Purpose
                        .FILE_DOWNLOAD
                    ),
                    ttl=timedelta(
                        minutes=10
                    ),
                )
            )

        resource_id = uuid.uuid4()

        issued = (
            RequestAccessTokenService
            .issue(
                request=self.request,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .FILE_DOWNLOAD
                ),
                ttl=timedelta(
                    minutes=10
                ),
                resource_type=(
                    RequestAccessToken
                    .ResourceType
                    .ATTACHMENT
                ),
                resource_id=resource_id,
            )
        )

        self.assertEqual(
            issued.record.resource_id,
            resource_id,
        )

    def test_portability_download_requires_export_binding(self):
        with self.assertRaises(
            TokenBindingError
        ):
            (
                RequestAccessTokenService
                .issue(
                    request=self.request,
                    purpose=(
                        RequestAccessToken
                        .Purpose
                        .PORTABILITY_DOWNLOAD
                    ),
                    ttl=timedelta(
                        minutes=10
                    ),
                    resource_type=(
                        RequestAccessToken
                        .ResourceType
                        .ATTACHMENT
                    ),
                    resource_id=(
                        uuid.uuid4()
                    ),
                )
            )

    def test_validate_accepts_correct_token(self):
        issued = self.issue_tracking()

        result = (
            RequestAccessTokenService
            .validate(
                request=self.request,
                token=issued.token,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .TRACKING
                ),
            )
        )

        self.assertEqual(
            result.pk,
            issued.record.pk,
        )

        self.assertIsNotNone(
            result.last_used_at
        )

        self.assertEqual(
            result.failed_attempts,
            0,
        )

    def test_invalid_token_uses_generic_error_and_increments_attempts(self):
        issued = self.issue_tracking()

        with self.assertRaises(
            TokenInvalidOrExpiredError
        ):
            (
                RequestAccessTokenService
                .validate(
                    request=self.request,
                    token=(
                        "invalid-token"
                    ),
                    purpose=(
                        RequestAccessToken
                        .Purpose
                        .TRACKING
                    ),
                )
            )

        issued.record.refresh_from_db()

        self.assertEqual(
            issued.record
            .failed_attempts,
            1,
        )

    def test_five_failures_temporarily_lock_token(self):
        issued = self.issue_tracking()

        for _ in range(5):
            with self.assertRaises(
                TokenInvalidOrExpiredError
            ):
                (
                    RequestAccessTokenService
                    .validate(
                        request=self.request,
                        token="wrong-token",
                        purpose=(
                            RequestAccessToken
                            .Purpose
                            .TRACKING
                        ),
                    )
                )

        issued.record.refresh_from_db()

        self.assertEqual(
            issued.record
            .failed_attempts,
            5,
        )

        self.assertIsNotNone(
            issued.record.locked_until
        )

        with self.assertRaises(
            TokenInvalidOrExpiredError
        ):
            (
                RequestAccessTokenService
                .validate(
                    request=self.request,
                    token=issued.token,
                    purpose=(
                        RequestAccessToken
                        .Purpose
                        .TRACKING
                    ),
                )
            )

    def test_revoked_token_is_rejected(self):
        issued = self.issue_tracking()

        RequestAccessTokenService.revoke(
            access_token=issued.record
        )

        with self.assertRaises(
            TokenInvalidOrExpiredError
        ):
            (
                RequestAccessTokenService
                .validate(
                    request=self.request,
                    token=issued.token,
                    purpose=(
                        RequestAccessToken
                        .Purpose
                        .TRACKING
                    ),
                )
            )

    def test_consume_makes_token_single_use(self):
        issued = (
            RequestAccessTokenService
            .issue(
                request=self.request,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .EMAIL_VERIFICATION
                ),
                ttl=timedelta(
                    minutes=15
                ),
            )
        )

        consumed = (
            RequestAccessTokenService
            .consume(
                request=self.request,
                token=issued.token,
                purpose=(
                    RequestAccessToken
                    .Purpose
                    .EMAIL_VERIFICATION
                ),
            )
        )

        self.assertIsNotNone(
            consumed.revoked_at
        )

        with self.assertRaises(
            TokenInvalidOrExpiredError
        ):
            (
                RequestAccessTokenService
                .validate(
                    request=self.request,
                    token=issued.token,
                    purpose=(
                        RequestAccessToken
                        .Purpose
                        .EMAIL_VERIFICATION
                    ),
                )
            )

    def test_new_token_revokes_previous_token_in_same_scope(self):
        first = self.issue_tracking()
        second = self.issue_tracking()

        first.record.refresh_from_db()

        self.assertIsNotNone(
            first.record.revoked_at
        )

        self.assertIsNone(
            second.record.revoked_at
        )

        with self.assertRaises(
            TokenInvalidOrExpiredError
        ):
            (
                RequestAccessTokenService
                .validate(
                    request=self.request,
                    token=first.token,
                    purpose=(
                        RequestAccessToken
                        .Purpose
                        .TRACKING
                    ),
                )
            )

    def test_expired_token_is_rejected(self):
        issued = self.issue_tracking()

        future = (
            issued.record.expires_at
            + timedelta(seconds=1)
        )

        with patch.object(
            RequestAccessTokenService,
            "_database_now",
            return_value=future,
        ):
            with self.assertRaises(
                TokenInvalidOrExpiredError
            ):
                (
                    RequestAccessTokenService
                    .validate(
                        request=self.request,
                        token=issued.token,
                        purpose=(
                            RequestAccessToken
                            .Purpose
                            .TRACKING
                        ),
                    )
                )

    def test_audit_never_contains_raw_token(self):
        issued = self.issue_tracking()

        audit = AuditLog.objects.get(
            action=(
                "REQUEST_ACCESS_TOKEN_ISSUED"
            ),
            entity_pk=str(
                issued.record.id
            ),
        )

        serialized = str(
            {
                "metadata": (
                    audit.metadata
                ),
                "previous_values": (
                    audit.previous_values
                ),
                "new_values": (
                    audit.new_values
                ),
                "description": (
                    audit.description
                ),
            }
        )

        self.assertNotIn(
            issued.token,
            serialized,
        )

        self.assertNotIn(
            issued.record.token_hash,
            serialized,
        )
