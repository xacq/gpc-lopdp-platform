import base64
from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.cases.models import (
    RequestClarification,
    RequestDeadline,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.cases.services.deadlines import (
    ClarificationLegalBasisError,
    ClarificationStateError,
    DeadlineAlreadyInitializedError,
    DeadlineExtensionAlreadyAppliedError,
    DeadlineExtensionNotAllowedError,
    DeadlineRuleError,
    DeadlineService,
)
from apps.legal_content.models import (
    RightCatalog,
    RightRule,
)
from apps.organization.models import SystemSetting
from apps.retention.models import BusinessHoliday
from apps.subjects.services.subjects import (
    SubjectService,
)


ENCRYPTION_KEY = base64.b64encode(
    b"G" * 32
).decode("ascii")

LOOKUP_KEY = base64.b64encode(
    b"H" * 32
).decode("ascii")

ECUADOR_TZ = ZoneInfo(
    "America/Guayaquil"
)


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
class DeadlineServiceTests(TestCase):

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

    def create_request_at(
        self,
        received_at: datetime,
    ):
        request = (
            CaseWorkflowService
            .create_request(
                data_subject=self.subject,
                right=self.right,
                request_details="Prueba",
            )
        )

        RightsRequest.objects.filter(
            pk=request.pk
        ).update(
            received_at=received_at
        )

        request.refresh_from_db()

        return request

    def create_actor(
        self,
        email="deadline@example.com",
    ):
        user_model = get_user_model()

        return user_model.objects.create_user(
            email=email,
            password="TestPassword123!",
            full_name="Responsable Plazos",
            is_active=True,
        )

    def test_business_days_skip_weekend(self):
        request = self.create_request_at(
            datetime(
                2026,
                8,
                14,
                10,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        deadline = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        due_local = (
            deadline.due_at
            .astimezone(ECUADOR_TZ)
        )

        self.assertEqual(
            due_local.date().isoformat(),
            "2026-08-21",
        )

    def test_business_days_skip_registered_holiday(self):
        BusinessHoliday.objects.create(
            holiday_date="2026-08-19",
            description="Feriado de prueba",
            is_national=True,
        )

        request = self.create_request_at(
            datetime(
                2026,
                8,
                14,
                10,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        deadline = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        due_local = (
            deadline.due_at
            .astimezone(ECUADOR_TZ)
        )

        self.assertEqual(
            due_local.date().isoformat(),
            "2026-08-24",
        )

    def test_calendar_days_include_weekend(self):
        self.rule.day_count_type = (
            RightRule
            .DayCountType
            .CALENDAR
        )
        self.rule.save(
            update_fields=[
                "day_count_type"
            ]
        )

        request = self.create_request_at(
            datetime(
                2026,
                8,
                14,
                10,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        deadline = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        due_local = (
            deadline.due_at
            .astimezone(ECUADOR_TZ)
        )

        self.assertEqual(
            due_local.date().isoformat(),
            "2026-08-19",
        )

    def test_warning_uses_same_business_calendar(self):
        request = self.create_request_at(
            datetime(
                2026,
                8,
                14,
                10,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        deadline = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        warning_local = (
            deadline.warning_at
            .astimezone(ECUADOR_TZ)
        )

        self.assertEqual(
            warning_local
            .date()
            .isoformat(),
            "2026-08-19",
        )

    def test_initial_deadline_updates_request_due_at(self):
        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                30,
                tzinfo=ECUADOR_TZ,
            )
        )

        deadline = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        request.refresh_from_db()

        self.assertEqual(
            request.current_due_at,
            deadline.due_at,
        )

        self.assertEqual(
            deadline.deadline_type,
            RequestDeadline
            .DeadlineType
            .INITIAL,
        )

        self.assertEqual(
            deadline.status,
            RequestDeadline
            .Status
            .ACTIVE,
        )

    def test_rule_snapshot_is_persisted(self):
        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                30,
                tzinfo=ECUADOR_TZ,
            )
        )

        deadline = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        snapshot = (
            deadline.rule_snapshot
        )

        self.assertEqual(
            snapshot["right_code"],
            "TEST_RIGHT",
        )
        self.assertEqual(
            snapshot["response_days"],
            5,
        )
        self.assertEqual(
            snapshot["warning_days"],
            2,
        )
        self.assertEqual(
            snapshot[
                "counting_convention"
            ],
            "EXCLUDE_START_DATE",
        )
        self.assertEqual(
            snapshot["timezone"],
            "America/Guayaquil",
        )

    def test_initial_deadline_generates_audit_entry(self):
        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                30,
                tzinfo=ECUADOR_TZ,
            )
        )

        deadline = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        audit = AuditLog.objects.get(
            action=(
                "REQUEST_DEADLINE_INITIALIZED"
            ),
            entity_pk=str(request.id),
        )

        self.assertEqual(
            audit.metadata[
                "reference_number"
            ],
            request.reference_number,
        )
        self.assertEqual(
            audit.metadata[
                "deadline_type"
            ],
            "INITIAL",
        )
        self.assertEqual(
            audit.metadata[
                "right_code"
            ],
            "TEST_RIGHT",
        )
        self.assertEqual(
            audit.metadata["due_at"],
            deadline.due_at.isoformat(),
        )

    def test_duplicate_initialization_is_rejected(self):
        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                30,
                tzinfo=ECUADOR_TZ,
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        with self.assertRaises(
            DeadlineAlreadyInitializedError
        ):
            (
                DeadlineService
                .initialize_initial(
                    request=request
                )
            )

        self.assertEqual(
            RequestDeadline.objects
            .filter(
                request=request,
                deadline_type=(
                    RequestDeadline
                    .DeadlineType
                    .INITIAL
                ),
            )
            .count(),
            1,
        )

    def test_missing_active_rule_is_rejected(self):
        self.rule.is_active = False
        self.rule.save(
            update_fields=[
                "is_active"
            ]
        )

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                30,
                tzinfo=ECUADOR_TZ,
            )
        )

        with self.assertRaises(
            DeadlineRuleError
        ):
            (
                DeadlineService
                .initialize_initial(
                    request=request
                )
            )

        request.refresh_from_db()

        self.assertIsNone(
            request.current_due_at
        )
        self.assertEqual(
            RequestDeadline.objects.count(),
            0,
        )

    def test_extension_updates_due_date_and_request(self):
        actor = self.create_actor()

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        initial = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        extension = (
            DeadlineService
            .apply_extension(
                request=request,
                reason=(
                    "Complejidad del caso"
                ),
                actor=actor,
            )
        )

        request.refresh_from_db()
        initial.refresh_from_db()

        self.assertEqual(
            initial.status,
            RequestDeadline
            .Status
            .COMPLETED,
        )

        self.assertEqual(
            extension.deadline_type,
            RequestDeadline
            .DeadlineType
            .EXTENSION,
        )

        self.assertEqual(
            extension.status,
            RequestDeadline
            .Status
            .ACTIVE,
        )

        self.assertTrue(
            request.extension_applied
        )

        self.assertEqual(
            request.current_due_at,
            extension.due_at,
        )

    def test_extension_reason_is_encrypted(self):
        actor = self.create_actor()

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        plaintext = (
            "Motivo reservado de extensión"
        )

        DeadlineService.apply_extension(
            request=request,
            reason=plaintext,
            actor=actor,
        )

        request.refresh_from_db()

        self.assertIsNotNone(
            request
            .extension_reason_encrypted
        )

        self.assertNotIn(
            plaintext.encode("utf-8"),
            bytes(
                request
                .extension_reason_encrypted
            ),
        )

    def test_extension_not_allowed_is_rejected(self):
        actor = self.create_actor()

        self.rule.extension_allowed = False
        self.rule.extension_days = 0
        self.rule.save(
            update_fields=[
                "extension_allowed",
                "extension_days",
            ]
        )

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        with self.assertRaises(
            DeadlineExtensionNotAllowedError
        ):
            DeadlineService.apply_extension(
                request=request,
                reason="No debe aplicar",
                actor=actor,
            )

    def test_extension_can_only_be_applied_once(self):
        actor = self.create_actor()

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        DeadlineService.apply_extension(
            request=request,
            reason="Primera extensión",
            actor=actor,
        )

        with self.assertRaises(
            DeadlineExtensionAlreadyAppliedError
        ):
            DeadlineService.apply_extension(
                request=request,
                reason="Segunda extensión",
                actor=actor,
            )

    def test_no_change_clarification_keeps_deadline_active(self):
        actor = self.create_actor()

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        initial = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        clarification = (
            DeadlineService
            .request_clarification(
                request=request,
                message=(
                    "Aclare la información."
                ),
                actor=actor,
            )
        )

        request.refresh_from_db()
        initial.refresh_from_db()

        self.assertEqual(
            clarification.deadline_effect,
            RightRule
            .ClarificationEffect
            .NO_CHANGE,
        )

        self.assertEqual(
            initial.status,
            RequestDeadline
            .Status
            .ACTIVE,
        )

        self.assertEqual(
            request.current_due_at,
            initial.due_at,
        )

    def test_pause_clarification_pauses_deadline(self):
        actor = self.create_actor()

        self.rule.clarification_effect = (
            RightRule
            .ClarificationEffect
            .PAUSE
        )
        self.rule.save(
            update_fields=[
                "clarification_effect"
            ]
        )

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        initial = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        clarification = (
            DeadlineService
            .request_clarification(
                request=request,
                message="Aclare el documento.",
                legal_basis=(
                    "Base jurídica de prueba"
                ),
                actor=actor,
            )
        )

        request.refresh_from_db()
        initial.refresh_from_db()

        self.assertEqual(
            clarification.deadline_effect,
            "PAUSE",
        )
        self.assertEqual(
            initial.status,
            RequestDeadline
            .Status
            .PAUSED,
        )
        self.assertIsNotNone(
            initial.paused_at
        )
        self.assertIsNone(
            request.current_due_at
        )

    def test_pause_clarification_resumes_deadline(self):
        actor = self.create_actor()

        self.rule.clarification_effect = (
            RightRule
            .ClarificationEffect
            .PAUSE
        )
        self.rule.save(
            update_fields=[
                "clarification_effect"
            ]
        )

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        initial = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        clarification = (
            DeadlineService
            .request_clarification(
                request=request,
                message="Aclare.",
                legal_basis="Base jurídica",
                actor=actor,
            )
        )

        old_due_at = initial.due_at

        clarification = (
            DeadlineService
            .receive_clarification(
                clarification=clarification,
                response_message=(
                    "Información aclarada."
                ),
                actor=actor,
            )
        )

        request.refresh_from_db()
        initial.refresh_from_db()

        self.assertEqual(
            clarification.status,
            RequestClarification
            .Status
            .RECEIVED,
        )
        self.assertEqual(
            initial.status,
            RequestDeadline
            .Status
            .ACTIVE,
        )
        self.assertIsNotNone(
            initial.resumed_at
        )
        self.assertIsNotNone(
            request.current_due_at
        )
        self.assertGreaterEqual(
            initial.due_at,
            old_due_at,
        )

        decrypted = (
            DeadlineService
            .decrypt_clarification_response(
                clarification
            )
        )

        self.assertEqual(
            decrypted,
            "Información aclarada.",
        )

    def test_restart_clarification_creates_new_deadline(self):
        actor = self.create_actor()

        self.rule.clarification_effect = (
            RightRule
            .ClarificationEffect
            .RESTART
        )
        self.rule.save(
            update_fields=[
                "clarification_effect"
            ]
        )

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        initial = (
            DeadlineService
            .initialize_initial(
                request=request
            )
        )

        clarification = (
            DeadlineService
            .request_clarification(
                request=request,
                message="Complete información.",
                legal_basis="Base jurídica",
                actor=actor,
            )
        )

        clarification = (
            DeadlineService
            .receive_clarification(
                clarification=clarification,
                response_message=(
                    "Información completada."
                ),
                actor=actor,
            )
        )

        request.refresh_from_db()
        initial.refresh_from_db()

        restarted = (
            RequestDeadline.objects.get(
                request=request,
                deadline_type=(
                    RequestDeadline
                    .DeadlineType
                    .CLARIFICATION
                ),
            )
        )

        self.assertEqual(
            initial.status,
            RequestDeadline
            .Status
            .COMPLETED,
        )

        self.assertEqual(
            restarted.status,
            RequestDeadline
            .Status
            .ACTIVE,
        )

        self.assertEqual(
            request.current_due_at,
            restarted.due_at,
        )

        self.assertEqual(
            restarted.rule_snapshot[
                "restart_source"
            ],
            "CLARIFICATION_RECEIVED",
        )

    def test_pause_or_restart_requires_legal_basis(self):
        actor = self.create_actor()

        self.rule.clarification_effect = (
            RightRule
            .ClarificationEffect
            .PAUSE
        )
        self.rule.save(
            update_fields=[
                "clarification_effect"
            ]
        )

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        with self.assertRaises(
            ClarificationLegalBasisError
        ):
            DeadlineService.request_clarification(
                request=request,
                message="Aclare.",
                actor=actor,
            )

    def test_clarification_cannot_be_received_twice(self):
        actor = self.create_actor()

        request = self.create_request_at(
            datetime(
                2026,
                8,
                17,
                9,
                0,
                tzinfo=ECUADOR_TZ,
            )
        )

        DeadlineService.initialize_initial(
            request=request
        )

        clarification = (
            DeadlineService
            .request_clarification(
                request=request,
                message="Aclare.",
                actor=actor,
            )
        )

        clarification = (
            DeadlineService
            .receive_clarification(
                clarification=clarification,
                response_message="Respuesta.",
                actor=actor,
            )
        )

        with self.assertRaises(
            ClarificationStateError
        ):
            DeadlineService.receive_clarification(
                clarification=clarification,
                response_message=(
                    "Segunda respuesta."
                ),
                actor=actor,
            )

