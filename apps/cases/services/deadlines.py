from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import connection, transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import (
    RequestDeadline,
    RightsRequest,
)
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
