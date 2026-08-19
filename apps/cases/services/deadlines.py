from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import (
    RequestClarification,
    RequestDeadline,
    RightsRequest,
)
from apps.core.services.crypto import CryptoService
from apps.legal_content.models import RightRule
from apps.organization.models import SystemSetting
from apps.retention.models import BusinessHoliday


class DeadlineServiceError(Exception):
    pass


class DeadlineConfigurationError(
    DeadlineServiceError
):
    pass


class DeadlineRuleError(
    DeadlineServiceError
):
    def __init__(self, right_id):
        self.right_id = right_id

        super().__init__(
            "No active deadline rule exists "
            f"for right: {right_id}"
        )


class DeadlineAlreadyInitializedError(
    DeadlineServiceError
):
    def __init__(self, request_id):
        self.request_id = request_id

        super().__init__(
            "Initial deadline already exists "
            f"for request: {request_id}"
        )


class DeadlineActorError(
    DeadlineServiceError
):
    pass


class DeadlineExtensionNotAllowedError(
    DeadlineServiceError
):
    pass


class DeadlineExtensionAlreadyAppliedError(
    DeadlineServiceError
):
    pass


class ClarificationLegalBasisError(
    DeadlineServiceError
):
    pass


class ClarificationStateError(
    DeadlineServiceError
):
    pass


class ActiveDeadlineRequiredError(
    DeadlineServiceError
):
    pass


class DeadlineService:
    COUNTING_CONVENTION = (
        "EXCLUDE_START_DATE"
    )

    @classmethod
    def _get_system_setting(
        cls,
    ) -> SystemSetting:
        setting = (
            SystemSetting.objects
            .filter(singleton_key=1)
            .first()
        )

        if setting is None:
            raise DeadlineConfigurationError(
                "SystemSetting singleton "
                "is required."
            )

        try:
            ZoneInfo(setting.timezone)
        except Exception as exc:
            raise DeadlineConfigurationError(
                "Invalid system timezone: "
                f"{setting.timezone}"
            ) from exc

        return setting

    @classmethod
    def _get_active_rule(
        cls,
        request: RightsRequest,
    ) -> RightRule:
        rule = (
            RightRule.objects
            .filter(
                right_id=request.right_id,
                is_active=True,
            )
            .first()
        )

        if rule is None:
            raise DeadlineRuleError(
                request.right_id
            )

        return rule

    @classmethod
    def _database_now(cls):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "transaction_timestamp()"
            )
            row = cursor.fetchone()

        return row[0]

    @classmethod
    def _holiday_dates(
        cls,
    ) -> set[date]:
        return set(
            BusinessHoliday.objects
            .values_list(
                "holiday_date",
                flat=True,
            )
        )

    @classmethod
    def _is_business_day(
        cls,
        value: date,
        *,
        holidays: set[date],
    ) -> bool:
        return (
            value.weekday() < 5
            and value not in holidays
        )

    @classmethod
    def _add_business_days(
        cls,
        start_date: date,
        days: int,
        *,
        holidays: set[date],
    ) -> date:
        current = start_date
        remaining = days

        while remaining > 0:
            current += timedelta(days=1)

            if cls._is_business_day(
                current,
                holidays=holidays,
            ):
                remaining -= 1

        return current

    @classmethod
    def _subtract_business_days(
        cls,
        start_date: date,
        days: int,
        *,
        holidays: set[date],
    ) -> date:
        current = start_date
        remaining = days

        while remaining > 0:
            current -= timedelta(days=1)

            if cls._is_business_day(
                current,
                holidays=holidays,
            ):
                remaining -= 1

        return current

    @classmethod
    def _combine_local_date(
        cls,
        *,
        target_date: date,
        template_local: datetime,
        timezone: ZoneInfo,
    ) -> datetime:
        local_time = (
            template_local
            .timetz()
            .replace(tzinfo=None)
        )

        return datetime.combine(
            target_date,
            local_time,
            tzinfo=timezone,
        )

    @classmethod
    def _calculate_due_at(
        cls,
        *,
        starts_at: datetime,
        rule: RightRule,
        timezone: ZoneInfo,
        holidays: set[date],
    ) -> datetime:
        local_start = starts_at.astimezone(
            timezone
        )

        if (
            rule.day_count_type
            == RightRule.DayCountType.CALENDAR
        ):
            due_date = (
                local_start.date()
                + timedelta(
                    days=rule.response_days
                )
            )

        elif (
            rule.day_count_type
            == RightRule.DayCountType.BUSINESS
        ):
            due_date = cls._add_business_days(
                local_start.date(),
                rule.response_days,
                holidays=holidays,
            )

        else:
            raise DeadlineRuleError(
                rule.right_id
            )

        return cls._combine_local_date(
            target_date=due_date,
            template_local=local_start,
            timezone=timezone,
        )

    @classmethod
    def _calculate_warning_at(
        cls,
        *,
        starts_at: datetime,
        due_at: datetime,
        rule: RightRule,
        timezone: ZoneInfo,
        holidays: set[date],
    ) -> datetime:
        if rule.warning_days == 0:
            return due_at

        local_start = starts_at.astimezone(
            timezone
        )

        local_due = due_at.astimezone(
            timezone
        )

        if (
            rule.day_count_type
            == RightRule.DayCountType.CALENDAR
        ):
            warning_date = (
                local_due.date()
                - timedelta(
                    days=rule.warning_days
                )
            )

        elif (
            rule.day_count_type
            == RightRule.DayCountType.BUSINESS
        ):
            warning_date = (
                cls._subtract_business_days(
                    local_due.date(),
                    rule.warning_days,
                    holidays=holidays,
                )
            )

        else:
            raise DeadlineRuleError(
                rule.right_id
            )

        warning_at = cls._combine_local_date(
            target_date=warning_date,
            template_local=local_due,
            timezone=timezone,
        )

        if warning_at < local_start:
            return local_start

        return warning_at

    @classmethod
    def _rule_snapshot(
        cls,
        *,
        rule: RightRule,
        timezone_name: str,
    ) -> dict:
        return {
            "right_id": str(
                rule.right_id
            ),
            "right_code": (
                rule.right.code
            ),
            "response_days": (
                rule.response_days
            ),
            "day_count_type": (
                rule.day_count_type
            ),
            "extension_allowed": (
                rule.extension_allowed
            ),
            "extension_days": (
                rule.extension_days
            ),
            "warning_days": (
                rule.warning_days
            ),
            "clarification_effect": (
                rule.clarification_effect
            ),
            "timezone": timezone_name,
            "counting_convention": (
                cls.COUNTING_CONVENTION
            ),
        }

    @classmethod
    def _validate_actor(
        cls,
        actor,
    ):
        actor_id = getattr(
            actor,
            "pk",
            None,
        )

        if actor_id is None:
            raise DeadlineActorError(
                "Deadline operation requires "
                "an active persisted user."
            )

        user_model = get_user_model()

        persisted_actor = (
            user_model.objects
            .filter(
                pk=actor_id,
                is_active=True,
            )
            .first()
        )

        if persisted_actor is None:
            raise DeadlineActorError(
                "Deadline operation requires "
                "an active persisted user."
            )

        return persisted_actor

    @classmethod
    def _active_deadline(
        cls,
        request: RightsRequest,
    ) -> RequestDeadline:
        deadline = (
            RequestDeadline.objects
            .filter(
                request=request,
                status=(
                    RequestDeadline
                    .Status
                    .ACTIVE
                ),
            )
            .order_by(
                "-sequence_number",
                "-created_at",
            )
            .first()
        )

        if deadline is None:
            raise ActiveDeadlineRequiredError(
                "An active request deadline "
                "is required."
            )

        return deadline

    @classmethod
    def _paused_deadline(
        cls,
        request: RightsRequest,
    ) -> RequestDeadline:
        deadline = (
            RequestDeadline.objects
            .filter(
                request=request,
                status=(
                    RequestDeadline
                    .Status
                    .PAUSED
                ),
            )
            .order_by(
                "-sequence_number",
                "-created_at",
            )
            .first()
        )

        if deadline is None:
            raise ActiveDeadlineRequiredError(
                "A paused request deadline "
                "is required."
            )

        return deadline

    @classmethod
    def _due_from_snapshot(
        cls,
        *,
        starts_at: datetime,
        snapshot: dict,
        timezone: ZoneInfo,
        holidays: set[date],
        days_key: str = "response_days",
    ) -> datetime:
        days = int(
            snapshot[days_key]
        )

        day_count_type = snapshot[
            "day_count_type"
        ]

        local_start = starts_at.astimezone(
            timezone
        )

        if (
            day_count_type
            == RightRule.DayCountType.CALENDAR
        ):
            due_date = (
                local_start.date()
                + timedelta(days=days)
            )

        elif (
            day_count_type
            == RightRule.DayCountType.BUSINESS
        ):
            due_date = cls._add_business_days(
                local_start.date(),
                days,
                holidays=holidays,
            )

        else:
            raise DeadlineRuleError(
                snapshot.get("right_id")
            )

        return cls._combine_local_date(
            target_date=due_date,
            template_local=local_start,
            timezone=timezone,
        )

    @classmethod
    def _warning_from_snapshot(
        cls,
        *,
        starts_at: datetime,
        due_at: datetime,
        snapshot: dict,
        timezone: ZoneInfo,
        holidays: set[date],
    ) -> datetime:
        warning_days = int(
            snapshot["warning_days"]
        )

        if warning_days == 0:
            return due_at

        local_start = starts_at.astimezone(
            timezone
        )
        local_due = due_at.astimezone(
            timezone
        )

        day_count_type = snapshot[
            "day_count_type"
        ]

        if (
            day_count_type
            == RightRule.DayCountType.CALENDAR
        ):
            warning_date = (
                local_due.date()
                - timedelta(
                    days=warning_days
                )
            )
        elif (
            day_count_type
            == RightRule.DayCountType.BUSINESS
        ):
            warning_date = (
                cls._subtract_business_days(
                    local_due.date(),
                    warning_days,
                    holidays=holidays,
                )
            )
        else:
            raise DeadlineRuleError(
                snapshot.get("right_id")
            )

        warning_at = cls._combine_local_date(
            target_date=warning_date,
            template_local=local_due,
            timezone=timezone,
        )

        if warning_at < local_start:
            return local_start

        return warning_at

    @classmethod
    def _remaining_counted_days(
        cls,
        *,
        paused_at: datetime,
        due_at: datetime,
        snapshot: dict,
        timezone: ZoneInfo,
        holidays: set[date],
    ) -> int:
        local_pause = paused_at.astimezone(
            timezone
        )
        local_due = due_at.astimezone(
            timezone
        )

        if local_due <= local_pause:
            return 0

        day_count_type = snapshot[
            "day_count_type"
        ]

        if (
            day_count_type
            == RightRule.DayCountType.CALENDAR
        ):
            return max(
                (
                    local_due.date()
                    - local_pause.date()
                ).days,
                0,
            )

        if (
            day_count_type
            == RightRule.DayCountType.BUSINESS
        ):
            current = local_pause.date()
            remaining = 0

            while current < local_due.date():
                current += timedelta(days=1)

                if cls._is_business_day(
                    current,
                    holidays=holidays,
                ):
                    remaining += 1

            return remaining

        raise DeadlineRuleError(
            snapshot.get("right_id")
        )

    @classmethod
    def _encrypt_extension_reason(
        cls,
        *,
        request: RightsRequest,
        reason: str,
    ) -> bytes:
        reason = reason.strip()

        if not reason:
            raise ValueError(
                "extension reason is required."
            )

        encrypted = CryptoService.encrypt_text(
            reason,
            aad=(
                f"rights_requests:"
                f"{request.id}:"
                f"extension_reason"
            ),
            key_version=(
                request.encryption_key_version
            ),
        )

        return encrypted.data

    @classmethod
    def _encrypt_clarification_text(
        cls,
        *,
        clarification_id: uuid.UUID,
        field_name: str,
        value: str,
        key_version: int,
    ) -> bytes:
        value = value.strip()

        if not value:
            raise ValueError(
                f"{field_name} is required."
            )

        encrypted = CryptoService.encrypt_text(
            value,
            aad=(
                f"request_clarifications:"
                f"{clarification_id}:"
                f"{field_name}"
            ),
            key_version=key_version,
        )

        return encrypted.data

    @classmethod
    def initialize_initial(
        cls,
        *,
        request: RightsRequest,
        actor=None,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> RequestDeadline:
        system_setting = (
            cls._get_system_setting()
        )

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(
            correlation_id,
            uuid.UUID,
        ):
            correlation_id = uuid.UUID(
                str(correlation_id)
            )

        timezone = ZoneInfo(
            system_setting.timezone
        )

        holidays = cls._holiday_dates()

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .select_related("right")
                .get(pk=request.pk)
            )

            existing = (
                RequestDeadline.objects
                .filter(
                    request=locked_request,
                    deadline_type=(
                        RequestDeadline
                        .DeadlineType
                        .INITIAL
                    ),
                    sequence_number=1,
                )
                .first()
            )

            if existing is not None:
                raise (
                    DeadlineAlreadyInitializedError(
                        locked_request.id
                    )
                )

            rule = cls._get_active_rule(
                locked_request
            )

            starts_at = (
                locked_request.received_at
            )

            due_at = cls._calculate_due_at(
                starts_at=starts_at,
                rule=rule,
                timezone=timezone,
                holidays=holidays,
            )

            warning_at = (
                cls._calculate_warning_at(
                    starts_at=starts_at,
                    due_at=due_at,
                    rule=rule,
                    timezone=timezone,
                    holidays=holidays,
                )
            )

            snapshot = cls._rule_snapshot(
                rule=rule,
                timezone_name=(
                    system_setting.timezone
                ),
            )

            deadline = (
                RequestDeadline.objects.create(
                    request=locked_request,
                    deadline_type=(
                        RequestDeadline
                        .DeadlineType
                        .INITIAL
                    ),
                    sequence_number=1,
                    starts_at=starts_at,
                    due_at=due_at,
                    warning_at=warning_at,
                    status=(
                        RequestDeadline
                        .Status
                        .ACTIVE
                    ),
                    rule_snapshot=snapshot,
                )
            )

            db_now = cls._database_now()

            locked_request.current_due_at = (
                due_at
            )
            locked_request.updated_at = (
                db_now
            )

            locked_request.save(
                update_fields=[
                    "current_due_at",
                    "updated_at",
                ]
            )

            AuditService.write(
                actor_type=(
                    AuditLog.ActorType.USER
                    if actor is not None
                    else AuditLog.ActorType.SYSTEM
                ),
                actor=actor,
                source=(
                    AuditLog.Source.WEB
                    if actor is not None
                    else AuditLog.Source.SYSTEM
                ),
                correlation_id=(
                    correlation_id
                ),
                action=(
                    "REQUEST_DEADLINE_INITIALIZED"
                ),
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                entity_pk=(
                    locked_request.id
                ),
                description=(
                    "Initial request deadline "
                    "initialized."
                ),
                metadata={
                    "reference_number": (
                        locked_request
                        .reference_number
                    ),
                    "deadline_type": (
                        RequestDeadline
                        .DeadlineType
                        .INITIAL
                    ),
                    "sequence_number": 1,
                    "right_code": (
                        rule.right.code
                    ),
                    "day_count_type": (
                        rule.day_count_type
                    ),
                    "response_days": (
                        rule.response_days
                    ),
                    "warning_days": (
                        rule.warning_days
                    ),
                    "due_at": (
                        due_at.isoformat()
                    ),
                    "warning_at": (
                        warning_at.isoformat()
                    ),
                },
            )

            return deadline

    @classmethod
    def apply_extension(
        cls,
        *,
        request: RightsRequest,
        reason: str,
        actor,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> RequestDeadline:
        actor = cls._validate_actor(
            actor
        )

        system_setting = (
            cls._get_system_setting()
        )
        timezone = ZoneInfo(
            system_setting.timezone
        )
        holidays = cls._holiday_dates()

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(
            correlation_id,
            uuid.UUID,
        ):
            correlation_id = uuid.UUID(
                str(correlation_id)
            )

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .select_related("right")
                .get(pk=request.pk)
            )

            if locked_request.extension_applied:
                raise (
                    DeadlineExtensionAlreadyAppliedError(
                        "Extension already applied."
                    )
                )

            rule = cls._get_active_rule(
                locked_request
            )

            if (
                not rule.extension_allowed
                or rule.extension_days <= 0
            ):
                raise (
                    DeadlineExtensionNotAllowedError(
                        "Extension is not allowed "
                        "for this right."
                    )
                )

            active_deadline = (
                cls._active_deadline(
                    locked_request
                )
            )

            reason_encrypted = (
                cls._encrypt_extension_reason(
                    request=locked_request,
                    reason=reason,
                )
            )

            extension_snapshot = dict(
                active_deadline.rule_snapshot
            )
            extension_snapshot.update({
                "extension_days": (
                    rule.extension_days
                ),
                "extension_allowed": (
                    rule.extension_allowed
                ),
                "extension_base": (
                    "PRIOR_DUE_AT"
                ),
                "prior_deadline_id": str(
                    active_deadline.id
                ),
                "prior_due_at": (
                    active_deadline
                    .due_at
                    .isoformat()
                ),
            })

            extension_starts_at = (
                active_deadline.due_at
            )

            extension_due_at = (
                cls._due_from_snapshot(
                    starts_at=(
                        extension_starts_at
                    ),
                    snapshot={
                        **extension_snapshot,
                        "response_days": (
                            rule.extension_days
                        ),
                    },
                    timezone=timezone,
                    holidays=holidays,
                )
            )

            extension_warning_at = (
                cls._warning_from_snapshot(
                    starts_at=(
                        extension_starts_at
                    ),
                    due_at=(
                        extension_due_at
                    ),
                    snapshot=(
                        extension_snapshot
                    ),
                    timezone=timezone,
                    holidays=holidays,
                )
            )

            db_now = cls._database_now()

            active_deadline.status = (
                RequestDeadline
                .Status
                .COMPLETED
            )
            active_deadline.completed_at = (
                db_now
            )
            active_deadline.save(
                update_fields=[
                    "status",
                    "completed_at",
                ]
            )

            extension_deadline = (
                RequestDeadline.objects.create(
                    request=locked_request,
                    deadline_type=(
                        RequestDeadline
                        .DeadlineType
                        .EXTENSION
                    ),
                    sequence_number=1,
                    starts_at=(
                        extension_starts_at
                    ),
                    due_at=(
                        extension_due_at
                    ),
                    warning_at=(
                        extension_warning_at
                    ),
                    status=(
                        RequestDeadline
                        .Status
                        .ACTIVE
                    ),
                    rule_snapshot=(
                        extension_snapshot
                    ),
                )
            )

            locked_request.extension_applied = True
            locked_request.extension_reason_encrypted = (
                reason_encrypted
            )
            locked_request.current_due_at = (
                extension_due_at
            )
            locked_request.updated_at = db_now

            locked_request.save(
                update_fields=[
                    "extension_applied",
                    "extension_reason_encrypted",
                    "current_due_at",
                    "updated_at",
                ]
            )

            AuditService.write(
                actor_type=(
                    AuditLog.ActorType.USER
                ),
                actor=actor,
                source=AuditLog.Source.WEB,
                correlation_id=(
                    correlation_id
                ),
                action=(
                    "REQUEST_DEADLINE_EXTENDED"
                ),
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                entity_pk=(
                    locked_request.id
                ),
                description=(
                    "Request deadline extended."
                ),
                previous_values={
                    "current_due_at": (
                        active_deadline
                        .due_at
                        .isoformat()
                    ),
                    "extension_applied": False,
                },
                new_values={
                    "current_due_at": (
                        extension_due_at
                        .isoformat()
                    ),
                    "extension_applied": True,
                },
                metadata={
                    "reference_number": (
                        locked_request
                        .reference_number
                    ),
                    "extension_days": (
                        rule.extension_days
                    ),
                    "day_count_type": (
                        rule.day_count_type
                    ),
                },
            )

            return extension_deadline

    @classmethod
    def request_clarification(
        cls,
        *,
        request: RightsRequest,
        message: str,
        actor,
        legal_basis: str | None = None,
        clarification_due_at: (
            datetime | None
        ) = None,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> RequestClarification:
        actor = cls._validate_actor(
            actor
        )

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(
            correlation_id,
            uuid.UUID,
        ):
            correlation_id = uuid.UUID(
                str(correlation_id)
            )

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .select_related("right")
                .get(pk=request.pk)
            )

            rule = cls._get_active_rule(
                locked_request
            )

            effect = (
                rule.clarification_effect
            )

            if (
                effect
                != RightRule
                .ClarificationEffect
                .NO_CHANGE
            ):
                legal_basis = (
                    legal_basis or ""
                ).strip()

                if not legal_basis:
                    raise (
                        ClarificationLegalBasisError(
                            "legal_basis is required "
                            "for PAUSE/RESTART."
                        )
                    )
            else:
                legal_basis = (
                    (legal_basis or "").strip()
                    or None
                )

            db_now = cls._database_now()

            if (
                clarification_due_at
                is not None
                and clarification_due_at
                < db_now
            ):
                raise ValueError(
                    "clarification_due_at "
                    "cannot be in the past."
                )

            clarification_id = uuid.uuid4()
            key_version = (
                settings
                .PII_ENCRYPTION_ACTIVE_VERSION
            )

            request_message_encrypted = (
                cls._encrypt_clarification_text(
                    clarification_id=(
                        clarification_id
                    ),
                    field_name=(
                        "request_message"
                    ),
                    value=message,
                    key_version=key_version,
                )
            )

            clarification = (
                RequestClarification.objects.create(
                    id=clarification_id,
                    request=locked_request,
                    requested_at=db_now,
                    due_at=(
                        clarification_due_at
                    ),
                    status=(
                        RequestClarification
                        .Status
                        .REQUESTED
                    ),
                    request_message_encrypted=(
                        request_message_encrypted
                    ),
                    encryption_key_version=(
                        key_version
                    ),
                    deadline_effect=effect,
                    deadline_effect_legal_basis=(
                        legal_basis
                    ),
                    created_by=actor,
                )
            )

            if (
                effect
                in {
                    RightRule
                    .ClarificationEffect
                    .PAUSE,
                    RightRule
                    .ClarificationEffect
                    .RESTART,
                }
            ):
                active_deadline = (
                    cls._active_deadline(
                        locked_request
                    )
                )

                active_deadline.status = (
                    RequestDeadline
                    .Status
                    .PAUSED
                )
                active_deadline.paused_at = (
                    db_now
                )
                active_deadline.save(
                    update_fields=[
                        "status",
                        "paused_at",
                    ]
                )

                locked_request.current_due_at = None
                locked_request.updated_at = (
                    db_now
                )
                locked_request.save(
                    update_fields=[
                        "current_due_at",
                        "updated_at",
                    ]
                )

            AuditService.write(
                actor_type=(
                    AuditLog.ActorType.USER
                ),
                actor=actor,
                source=AuditLog.Source.WEB,
                correlation_id=(
                    correlation_id
                ),
                action=(
                    "REQUEST_CLARIFICATION_REQUESTED"
                ),
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                entity_pk=(
                    locked_request.id
                ),
                description=(
                    "Clarification requested."
                ),
                metadata={
                    "reference_number": (
                        locked_request
                        .reference_number
                    ),
                    "clarification_id": str(
                        clarification.id
                    ),
                    "deadline_effect": (
                        effect
                    ),
                },
            )

            return clarification

    @classmethod
    def receive_clarification(
        cls,
        *,
        clarification: RequestClarification,
        response_message: str,
        actor,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> RequestClarification:
        actor = cls._validate_actor(
            actor
        )

        system_setting = (
            cls._get_system_setting()
        )
        timezone = ZoneInfo(
            system_setting.timezone
        )
        holidays = cls._holiday_dates()

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(
            correlation_id,
            uuid.UUID,
        ):
            correlation_id = uuid.UUID(
                str(correlation_id)
            )

        with transaction.atomic():
            locked_clarification = (
                RequestClarification.objects
                .select_for_update()
                .select_related("request")
                .get(pk=clarification.pk)
            )

            if (
                locked_clarification.status
                != RequestClarification
                .Status
                .REQUESTED
            ):
                raise ClarificationStateError(
                    "Clarification is not "
                    "in REQUESTED status."
                )

            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .get(
                    pk=(
                        locked_clarification
                        .request_id
                    )
                )
            )

            db_now = cls._database_now()

            encrypted_response = (
                cls._encrypt_clarification_text(
                    clarification_id=(
                        locked_clarification.id
                    ),
                    field_name=(
                        "response_message"
                    ),
                    value=response_message,
                    key_version=(
                        locked_clarification
                        .encryption_key_version
                    ),
                )
            )

            effect = (
                locked_clarification
                .deadline_effect
            )

            if (
                effect
                == RightRule
                .ClarificationEffect
                .PAUSE
            ):
                paused_deadline = (
                    cls._paused_deadline(
                        locked_request
                    )
                )

                remaining_days = (
                    cls._remaining_counted_days(
                        paused_at=(
                            paused_deadline
                            .paused_at
                        ),
                        due_at=(
                            paused_deadline
                            .due_at
                        ),
                        snapshot=(
                            paused_deadline
                            .rule_snapshot
                        ),
                        timezone=timezone,
                        holidays=holidays,
                    )
                )

                resume_snapshot = dict(
                    paused_deadline.rule_snapshot
                )
                resume_snapshot[
                    "response_days"
                ] = remaining_days

                calculated_due_at = (
                    cls._due_from_snapshot(
                        starts_at=db_now,
                        snapshot=(
                            resume_snapshot
                        ),
                        timezone=timezone,
                        holidays=holidays,
                    )
                )
                new_due_at = max(
                    calculated_due_at,
                    paused_deadline.due_at,
                )

                new_warning_at = (
                    cls._warning_from_snapshot(
                        starts_at=db_now,
                        due_at=new_due_at,
                        snapshot=(
                            paused_deadline
                            .rule_snapshot
                        ),
                        timezone=timezone,
                        holidays=holidays,
                    )
                )

                paused_deadline.status = (
                    RequestDeadline
                    .Status
                    .ACTIVE
                )
                paused_deadline.resumed_at = (
                    db_now
                )
                paused_deadline.due_at = (
                    new_due_at
                )
                paused_deadline.warning_at = (
                    new_warning_at
                )
                paused_deadline.save(
                    update_fields=[
                        "status",
                        "resumed_at",
                        "due_at",
                        "warning_at",
                    ]
                )

                locked_request.current_due_at = (
                    new_due_at
                )

            elif (
                effect
                == RightRule
                .ClarificationEffect
                .RESTART
            ):
                paused_deadline = (
                    cls._paused_deadline(
                        locked_request
                    )
                )

                paused_deadline.status = (
                    RequestDeadline
                    .Status
                    .COMPLETED
                )
                paused_deadline.completed_at = (
                    db_now
                )
                paused_deadline.save(
                    update_fields=[
                        "status",
                        "completed_at",
                    ]
                )

                snapshot = dict(
                    paused_deadline.rule_snapshot
                )

                new_due_at = (
                    cls._due_from_snapshot(
                        starts_at=db_now,
                        snapshot=snapshot,
                        timezone=timezone,
                        holidays=holidays,
                    )
                )

                new_warning_at = (
                    cls._warning_from_snapshot(
                        starts_at=db_now,
                        due_at=new_due_at,
                        snapshot=snapshot,
                        timezone=timezone,
                        holidays=holidays,
                    )
                )

                last_sequence = (
                    RequestDeadline.objects
                    .filter(
                        request=locked_request,
                        deadline_type=(
                            RequestDeadline
                            .DeadlineType
                            .CLARIFICATION
                        ),
                    )
                    .order_by(
                        "-sequence_number"
                    )
                    .values_list(
                        "sequence_number",
                        flat=True,
                    )
                    .first()
                )

                next_sequence = (
                    (last_sequence or 0) + 1
                )

                RequestDeadline.objects.create(
                    request=locked_request,
                    deadline_type=(
                        RequestDeadline
                        .DeadlineType
                        .CLARIFICATION
                    ),
                    sequence_number=(
                        next_sequence
                    ),
                    starts_at=db_now,
                    due_at=new_due_at,
                    warning_at=(
                        new_warning_at
                    ),
                    status=(
                        RequestDeadline
                        .Status
                        .ACTIVE
                    ),
                    rule_snapshot={
                        **snapshot,
                        "restart_source": (
                            "CLARIFICATION_RECEIVED"
                        ),
                        "clarification_id": str(
                            locked_clarification.id
                        ),
                    },
                )

                locked_request.current_due_at = (
                    new_due_at
                )

            locked_request.updated_at = db_now
            locked_request.save(
                update_fields=[
                    "current_due_at",
                    "updated_at",
                ]
            )

            locked_clarification.status = (
                RequestClarification
                .Status
                .RECEIVED
            )
            locked_clarification.received_at = (
                db_now
            )
            locked_clarification.response_message_encrypted = (
                encrypted_response
            )
            locked_clarification.save(
                update_fields=[
                    "status",
                    "received_at",
                    "response_message_encrypted",
                ]
            )

            AuditService.write(
                actor_type=(
                    AuditLog.ActorType.USER
                ),
                actor=actor,
                source=AuditLog.Source.WEB,
                correlation_id=(
                    correlation_id
                ),
                action=(
                    "REQUEST_CLARIFICATION_RECEIVED"
                ),
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                entity_pk=(
                    locked_request.id
                ),
                description=(
                    "Clarification response "
                    "received."
                ),
                metadata={
                    "reference_number": (
                        locked_request
                        .reference_number
                    ),
                    "clarification_id": str(
                        locked_clarification.id
                    ),
                    "deadline_effect": effect,
                },
            )

            return locked_clarification

    @classmethod
    def decrypt_clarification_request(
        cls,
        clarification: RequestClarification,
    ) -> str:
        return CryptoService.decrypt_text(
            clarification
            .request_message_encrypted,
            aad=(
                f"request_clarifications:"
                f"{clarification.id}:"
                f"request_message"
            ),
            key_version=(
                clarification
                .encryption_key_version
            ),
        )

    @classmethod
    def decrypt_clarification_response(
        cls,
        clarification: RequestClarification,
    ) -> str | None:
        if not (
            clarification
            .response_message_encrypted
        ):
            return None

        return CryptoService.decrypt_text(
            clarification
            .response_message_encrypted,
            aad=(
                f"request_clarifications:"
                f"{clarification.id}:"
                f"response_message"
            ),
            key_version=(
                clarification
                .encryption_key_version
            ),
        )

    @classmethod
    def complete_current(
        cls,
        *,
        request: RightsRequest,
        actor,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> list[RequestDeadline]:
        actor = cls._validate_actor(
            actor
        )

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(
            correlation_id,
            uuid.UUID,
        ):
            correlation_id = uuid.UUID(
                str(correlation_id)
            )

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .get(pk=request.pk)
            )

            deadlines = list(
                RequestDeadline.objects
                .select_for_update()
                .filter(
                    request=locked_request,
                    status__in=[
                        RequestDeadline
                        .Status
                        .ACTIVE,
                        RequestDeadline
                        .Status
                        .PAUSED,
                    ],
                )
                .order_by(
                    "created_at",
                    "id",
                )
            )

            db_now = cls._database_now()

            completed_count = 0
            cancelled_count = 0

            for deadline in deadlines:
                if deadline.starts_at <= db_now:
                    deadline.status = (
                        RequestDeadline
                        .Status
                        .COMPLETED
                    )
                    deadline.completed_at = (
                        db_now
                    )
                    deadline.save(
                        update_fields=[
                            "status",
                            "completed_at",
                        ]
                    )
                    completed_count += 1
                else:
                    deadline.status = (
                        RequestDeadline
                        .Status
                        .CANCELLED
                    )
                    deadline.completed_at = (
                        None
                    )
                    deadline.save(
                        update_fields=[
                            "status",
                            "completed_at",
                        ]
                    )
                    cancelled_count += 1

            locked_request.current_due_at = (
                None
            )
            locked_request.updated_at = db_now
            locked_request.save(
                update_fields=[
                    "current_due_at",
                    "updated_at",
                ]
            )

            if deadlines:
                AuditService.write(
                    actor_type=(
                        AuditLog.ActorType.USER
                    ),
                    actor=actor,
                    source=AuditLog.Source.WEB,
                    correlation_id=(
                        correlation_id
                    ),
                    action=(
                        "REQUEST_DEADLINE_COMPLETED"
                    ),
                    entity_type=(
                        "RIGHTS_REQUEST"
                    ),
                    entity_pk=(
                        locked_request.id
                    ),
                    description=(
                        "Open request deadline "
                        "completed."
                    ),
                    metadata={
                        "reference_number": (
                            locked_request
                            .reference_number
                        ),
                        "completed_count": (
                            completed_count
                        ),
                        "cancelled_count": (
                            cancelled_count
                        ),
                    },
                )

            return deadlines

