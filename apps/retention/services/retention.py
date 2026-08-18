from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection, transaction

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import RightsRequest
from apps.retention.models import (
    DataDisposalEvent,
    RetentionRule,
)


class RetentionServiceError(Exception):
    pass


class RetentionRuleNotFoundError(
    RetentionServiceError
):
    pass


class RetentionPermissionError(
    RetentionServiceError
):
    pass


class RetentionEventStateError(
    RetentionServiceError
):
    pass


class RetentionService:
    ENTITY_RIGHTS_REQUEST = (
        "RIGHTS_REQUEST"
    )

    MANAGER_ROLE_CODES = {
        Role.Code.ADMIN,
        Role.Code.DPD,
        Role.Code.RESPONSABLE,
    }

    SUPPORTED_REQUEST_ANCHORS = {
        RetentionRule
        .RetentionAnchor
        .CREATED_AT: "created_at",
        RetentionRule
        .RetentionAnchor
        .RECEIVED_AT: "received_at",
        RetentionRule
        .RetentionAnchor
        .CLOSED_AT: "closed_at",
    }

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
    def _active_role_codes(
        cls,
        user,
    ) -> set[str]:
        return set(
            user.role_assignments
            .filter(
                revoked_at__isnull=True,
                role__is_active=True,
            )
            .values_list(
                "role__code",
                flat=True,
            )
        )

    @classmethod
    def _validate_manager(
        cls,
        actor,
    ):
        actor_id = getattr(
            actor,
            "pk",
            None,
        )

        if actor_id is None:
            raise RetentionPermissionError(
                "Active manager actor "
                "is required."
            )

        user_model = get_user_model()

        persisted = (
            user_model.objects
            .filter(
                pk=actor_id,
                is_active=True,
            )
            .first()
        )

        if persisted is None:
            raise RetentionPermissionError(
                "Active manager actor "
                "is required."
            )

        if persisted.is_superuser:
            return persisted

        if not (
            cls._active_role_codes(
                persisted
            )
            & cls.MANAGER_ROLE_CODES
        ):
            raise RetentionPermissionError(
                "Actor is not allowed "
                "to approve retention events."
            )

        return persisted

    @classmethod
    def _get_rule(
        cls,
        entity_type: str,
    ) -> RetentionRule:
        rule = (
            RetentionRule.objects
            .filter(
                entity_type=entity_type,
                is_active=True,
            )
            .first()
        )

        if rule is None:
            raise RetentionRuleNotFoundError(
                f"No active retention rule "
                f"for {entity_type}."
            )

        return rule

    @classmethod
    def _request_anchor(
        cls,
        *,
        request: RightsRequest,
        rule: RetentionRule,
    ):
        field_name = (
            cls.SUPPORTED_REQUEST_ANCHORS
            .get(rule.retention_anchor)
        )

        if field_name is None:
            raise RetentionServiceError(
                "Retention anchor is not "
                "supported for rights requests."
            )

        return getattr(
            request,
            field_name,
        )

    @classmethod
    def _audit(
        cls,
        *,
        action: str,
        event: DataDisposalEvent,
        actor=None,
        correlation_id=None,
    ) -> None:
        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(
            correlation_id,
            uuid.UUID,
        ):
            correlation_id = uuid.UUID(
                str(correlation_id)
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
            action=action,
            entity_type=(
                "DATA_DISPOSAL_EVENT"
            ),
            entity_pk=event.id,
            description=(
                "Retention lifecycle event."
            ),
            metadata={
                "entity_type": (
                    event.entity_type
                ),
                "entity_pk": (
                    event.entity_pk
                ),
                "action": event.action,
                "status": event.status,
            },
        )

    @classmethod
    def detect_rights_request(
        cls,
        *,
        request: RightsRequest,
        correlation_id=None,
    ) -> DataDisposalEvent | None:
        rule = cls._get_rule(
            cls.ENTITY_RIGHTS_REQUEST
        )

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .get(pk=request.pk)
            )

            anchor = cls._request_anchor(
                request=locked_request,
                rule=rule,
            )

            if anchor is None:
                return None

            db_now = cls._database_now()

            eligible_at = (
                anchor
                + timedelta(
                    days=(
                        rule.retention_days
                    )
                )
            )

            if db_now < eligible_at:
                return None

            existing = (
                DataDisposalEvent.objects
                .select_for_update()
                .filter(
                    entity_type=(
                        cls.ENTITY_RIGHTS_REQUEST
                    ),
                    entity_pk=str(
                        locked_request.id
                    ),
                    action=(
                        rule.final_action
                    ),
                    status__in=[
                        DataDisposalEvent
                        .Status
                        .DETECTED,
                        DataDisposalEvent
                        .Status
                        .PENDING_APPROVAL,
                        DataDisposalEvent
                        .Status
                        .APPROVED,
                    ],
                )
                .first()
            )

            if existing is not None:
                return existing

            if rule.requires_approval:
                status = (
                    DataDisposalEvent
                    .Status
                    .PENDING_APPROVAL
                )
                approved_at = None
            else:
                status = (
                    DataDisposalEvent
                    .Status
                    .APPROVED
                )
                approved_at = db_now

            event = (
                DataDisposalEvent.objects
                .create(
                    retention_rule=rule,
                    entity_type=(
                        cls.ENTITY_RIGHTS_REQUEST
                    ),
                    entity_pk=str(
                        locked_request.id
                    ),
                    action=(
                        rule.final_action
                    ),
                    status=status,
                    approved_at=(
                        approved_at
                    ),
                )
            )

            cls._audit(
                action=(
                    "DATA_DISPOSAL_EVENT_DETECTED"
                ),
                event=event,
                actor=None,
                correlation_id=(
                    correlation_id
                ),
            )

            return event

    @classmethod
    def approve(
        cls,
        *,
        event: DataDisposalEvent,
        actor,
        correlation_id=None,
    ) -> DataDisposalEvent:
        actor = cls._validate_manager(
            actor
        )

        with transaction.atomic():
            locked = (
                DataDisposalEvent.objects
                .select_for_update()
                .get(pk=event.pk)
            )

            if (
                locked.status
                != DataDisposalEvent
                .Status
                .PENDING_APPROVAL
            ):
                raise RetentionEventStateError(
                    "Only PENDING_APPROVAL "
                    "events can be approved."
                )

            db_now = cls._database_now()

            locked.status = (
                DataDisposalEvent
                .Status
                .APPROVED
            )
            locked.approved_by = actor
            locked.approved_at = db_now

            locked.save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                ]
            )

            cls._audit(
                action=(
                    "DATA_DISPOSAL_EVENT_APPROVED"
                ),
                event=locked,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
            )

            return locked


    @classmethod
    def _execution_evidence_hash(
        cls,
        *,
        event: DataDisposalEvent,
        actor,
        executed_at,
    ) -> str:
        payload = {
            "event_id": str(event.id),
            "entity_type": event.entity_type,
            "entity_pk": event.entity_pk,
            "action": event.action,
            "executed_by_id": str(
                actor.id
            ),
            "executed_at": (
                executed_at.isoformat()
            ),
        }

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(
            canonical
        ).hexdigest()

    @classmethod
    def execute(
        cls,
        *,
        event: DataDisposalEvent,
        actor,
        executor,
        correlation_id=None,
    ) -> DataDisposalEvent:
        actor = cls._validate_manager(
            actor
        )

        if not callable(executor):
            raise RetentionServiceError(
                "A callable retention executor "
                "is required."
            )

        with transaction.atomic():
            locked = (
                DataDisposalEvent.objects
                .select_for_update()
                .get(pk=event.pk)
            )

            if (
                locked.status
                == DataDisposalEvent
                .Status
                .EXECUTED
            ):
                return locked

            if (
                locked.status
                != DataDisposalEvent
                .Status
                .APPROVED
            ):
                raise RetentionEventStateError(
                    "Only APPROVED retention "
                    "events can be executed."
                )

            try:
                executor(
                    entity_type=(
                        locked.entity_type
                    ),
                    entity_pk=(
                        locked.entity_pk
                    ),
                    action=locked.action,
                )
            except Exception as exc:
                locked.status = (
                    DataDisposalEvent
                    .Status
                    .FAILED
                )
                locked.error_code = (
                    "RETENTION_EXECUTION_FAILED"
                )
                locked.error_message = (
                    exc.__class__.__name__[
                        :500
                    ]
                )
                locked.executed_by = None
                locked.executed_at = None
                locked.evidence_sha256 = None

                locked.save(
                    update_fields=[
                        "status",
                        "error_code",
                        "error_message",
                        "executed_by",
                        "executed_at",
                        "evidence_sha256",
                    ]
                )

                cls._audit(
                    action=(
                        "DATA_DISPOSAL_EVENT_FAILED"
                    ),
                    event=locked,
                    actor=actor,
                    correlation_id=(
                        correlation_id
                    ),
                )

                return locked

            db_now = cls._database_now()

            locked.status = (
                DataDisposalEvent
                .Status
                .EXECUTED
            )
            locked.executed_by = actor
            locked.executed_at = db_now
            locked.evidence_sha256 = (
                cls._execution_evidence_hash(
                    event=locked,
                    actor=actor,
                    executed_at=db_now,
                )
            )
            locked.error_code = None
            locked.error_message = None

            locked.save(
                update_fields=[
                    "status",
                    "executed_by",
                    "executed_at",
                    "evidence_sha256",
                    "error_code",
                    "error_message",
                ]
            )

            cls._audit(
                action=(
                    "DATA_DISPOSAL_EVENT_EXECUTED"
                ),
                event=locked,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
            )

            return locked

    @classmethod
    def retry_failed(
        cls,
        *,
        event: DataDisposalEvent,
        actor,
        correlation_id=None,
    ) -> DataDisposalEvent:
        actor = cls._validate_manager(
            actor
        )

        with transaction.atomic():
            locked = (
                DataDisposalEvent.objects
                .select_for_update()
                .get(pk=event.pk)
            )

            if (
                locked.status
                != DataDisposalEvent
                .Status
                .FAILED
            ):
                raise RetentionEventStateError(
                    "Only FAILED retention "
                    "events can be retried."
                )

            if locked.approved_at is None:
                raise RetentionEventStateError(
                    "Failed event has no "
                    "approval timestamp."
                )

            locked.status = (
                DataDisposalEvent
                .Status
                .APPROVED
            )
            locked.error_code = None
            locked.error_message = None

            locked.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                ]
            )

            cls._audit(
                action=(
                    "DATA_DISPOSAL_EVENT_RETRY_READY"
                ),
                event=locked,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
            )

            return locked

    @classmethod
    def reject(
        cls,
        *,
        event: DataDisposalEvent,
        actor,
        correlation_id=None,
    ) -> DataDisposalEvent:
        actor = cls._validate_manager(
            actor
        )

        with transaction.atomic():
            locked = (
                DataDisposalEvent.objects
                .select_for_update()
                .get(pk=event.pk)
            )

            if (
                locked.status
                not in {
                    DataDisposalEvent
                    .Status
                    .DETECTED,
                    DataDisposalEvent
                    .Status
                    .PENDING_APPROVAL,
                    DataDisposalEvent
                    .Status
                    .APPROVED,
                }
            ):
                raise RetentionEventStateError(
                    "Retention event cannot "
                    "be rejected from its "
                    "current state."
                )

            locked.status = (
                DataDisposalEvent
                .Status
                .REJECTED
            )

            locked.save(
                update_fields=[
                    "status",
                ]
            )

            cls._audit(
                action=(
                    "DATA_DISPOSAL_EVENT_REJECTED"
                ),
                event=locked,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
            )

            return locked
