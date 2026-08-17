from __future__ import annotations

import uuid

from django.conf import settings
from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import (
    CaseOutcomeReason,
    RequestClarification,
    RequestDeadline,
    RequestResolution,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseTransitionError,
    CaseWorkflowService,
)
from apps.cases.services.deadlines import (
    DeadlineService,
)
from apps.core.services.crypto import CryptoService


class ResolutionServiceError(Exception):
    pass


class ResolutionConflictError(
    ResolutionServiceError
):
    pass


class ResolutionReasonError(
    ResolutionServiceError
):
    pass


class ResolutionStateError(
    ResolutionServiceError
):
    pass


class ResolutionCloseBlockedError(
    ResolutionServiceError
):
    pass


class ResolutionService:
    REASON_TYPE_BY_RESOLUTION = {
        RequestResolution
        .ResolutionType
        .REJECTED: (
            CaseOutcomeReason
            .ReasonType
            .REJECTION
        ),
        RequestResolution
        .ResolutionType
        .ARCHIVED: (
            CaseOutcomeReason
            .ReasonType
            .ARCHIVE
        ),
        RequestResolution
        .ResolutionType
        .CANCELLED: (
            CaseOutcomeReason
            .ReasonType
            .CANCELLATION
        ),
    }

    RESOLUTION_STATUS = {
        RequestResolution
        .ResolutionType
        .PARTIALLY_APPROVED: (
            RightsRequest
            .Status
            .PARTIALLY_APPROVED
        ),
        RequestResolution
        .ResolutionType
        .REJECTED: (
            RightsRequest
            .Status
            .REJECTED
        ),
        RequestResolution
        .ResolutionType
        .ARCHIVED: (
            RightsRequest
            .Status
            .ARCHIVED
        ),
        RequestResolution
        .ResolutionType
        .CANCELLED: (
            RightsRequest
            .Status
            .CANCELLED
        ),
    }

    @classmethod
    def _normalize_correlation_id(
        cls,
        correlation_id,
    ) -> uuid.UUID:
        if correlation_id is None:
            return uuid.uuid4()

        if isinstance(
            correlation_id,
            uuid.UUID,
        ):
            return correlation_id

        return uuid.UUID(
            str(correlation_id)
        )

    @classmethod
    def _validate_manager(
        cls,
        actor,
    ):
        actor = (
            CaseWorkflowService
            ._validate_actor(actor)
        )

        if actor is None:
            raise ResolutionServiceError(
                "Resolution requires "
                "an actor."
            )

        CaseWorkflowService \
            ._require_manager_permission(
                actor
            )

        return actor

    @classmethod
    def _validate_resolution_type(
        cls,
        resolution_type: str,
    ) -> str:
        resolution_type = (
            resolution_type
            .strip()
            .upper()
        )

        valid = {
            choice[0]
            for choice in (
                RequestResolution
                .ResolutionType
                .choices
            )
        }

        if resolution_type not in valid:
            raise ValueError(
                "Invalid resolution_type: "
                f"{resolution_type}"
            )

        return resolution_type

    @classmethod
    def _validate_state(
        cls,
        *,
        request: RightsRequest,
        resolution_type: str,
    ) -> None:
        current = request.status

        substantive_states = {
            RightsRequest
            .Status
            .UNDER_REVIEW,
            RightsRequest
            .Status
            .EXTENDED,
        }

        if (
            resolution_type
            in {
                RequestResolution
                .ResolutionType
                .APPROVED,
                RequestResolution
                .ResolutionType
                .PARTIALLY_APPROVED,
                RequestResolution
                .ResolutionType
                .REJECTED,
            }
        ):
            if current not in (
                substantive_states
            ):
                raise ResolutionStateError(
                    "Substantive resolution "
                    "requires UNDER_REVIEW "
                    "or EXTENDED."
                )
            return

        if (
            resolution_type
            == RequestResolution
            .ResolutionType
            .ARCHIVED
        ):
            if (
                current
                != RightsRequest
                .Status
                .AWAITING_INFORMATION
            ):
                raise ResolutionStateError(
                    "Archive requires "
                    "AWAITING_INFORMATION."
                )

            expired_exists = (
                RequestClarification.objects
                .filter(
                    request=request,
                    status=(
                        RequestClarification
                        .Status
                        .EXPIRED
                    ),
                )
                .exists()
            )

            if not expired_exists:
                raise ResolutionStateError(
                    "Archive requires an "
                    "expired clarification."
                )
            return

        if (
            resolution_type
            == RequestResolution
            .ResolutionType
            .CANCELLED
        ):
            if (
                current
                != RightsRequest
                .Status
                .RECEIVED
            ):
                raise ResolutionStateError(
                    "Cancellation is only "
                    "allowed from RECEIVED."
                )
            return

        raise ResolutionStateError(
            "Unsupported resolution state."
        )

    @classmethod
    def _validate_reason(
        cls,
        *,
        resolution_type: str,
        outcome_reason: (
            CaseOutcomeReason | None
        ),
    ) -> (
        CaseOutcomeReason | None
    ):
        required_reason_type = (
            cls.REASON_TYPE_BY_RESOLUTION
            .get(resolution_type)
        )

        if required_reason_type is None:
            if outcome_reason is not None:
                raise ResolutionReasonError(
                    "This resolution type "
                    "does not accept an "
                    "outcome reason."
                )

            return None

        if outcome_reason is None:
            raise ResolutionReasonError(
                "An active outcome reason "
                "is required."
            )

        persisted = (
            CaseOutcomeReason.objects
            .filter(
                pk=outcome_reason.pk,
                is_active=True,
                reason_type=(
                    required_reason_type
                ),
            )
            .first()
        )

        if persisted is None:
            raise ResolutionReasonError(
                "Outcome reason is inactive "
                "or has the wrong type."
            )

        return persisted

    @classmethod
    def _encrypt_details(
        cls,
        *,
        resolution_id: uuid.UUID,
        details: str,
        key_version: int,
    ) -> bytes:
        details = details.strip()

        if not details:
            raise ValueError(
                "resolution details "
                "are required."
            )

        encrypted = (
            CryptoService.encrypt_text(
                details,
                aad=(
                    "request_resolutions:"
                    f"{resolution_id}:"
                    "resolution_details"
                ),
                key_version=key_version,
            )
        )

        return encrypted.data

    @classmethod
    def resolve(
        cls,
        *,
        request: RightsRequest,
        resolution_type: str,
        details: str,
        actor,
        outcome_reason: (
            CaseOutcomeReason | None
        ) = None,
        legal_basis: str | None = None,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> RequestResolution:
        actor = cls._validate_manager(
            actor
        )

        resolution_type = (
            cls._validate_resolution_type(
                resolution_type
            )
        )

        correlation_id = (
            cls._normalize_correlation_id(
                correlation_id
            )
        )

        legal_basis = (
            (legal_basis or "").strip()
            or None
        )

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .get(pk=request.pk)
            )

            if (
                RequestResolution.objects
                .filter(
                    request=locked_request
                )
                .exists()
            ):
                raise ResolutionConflictError(
                    "Request already has "
                    "a resolution."
                )

            cls._validate_state(
                request=locked_request,
                resolution_type=(
                    resolution_type
                ),
            )

            outcome_reason = (
                cls._validate_reason(
                    resolution_type=(
                        resolution_type
                    ),
                    outcome_reason=(
                        outcome_reason
                    ),
                )
            )

            resolution_id = uuid.uuid4()
            key_version = (
                settings
                .PII_ENCRYPTION_ACTIVE_VERSION
            )

            encrypted_details = (
                cls._encrypt_details(
                    resolution_id=(
                        resolution_id
                    ),
                    details=details,
                    key_version=key_version,
                )
            )

            db_now = (
                CaseWorkflowService
                ._database_now()
            )

            resolution = (
                RequestResolution.objects
                .create(
                    id=resolution_id,
                    request=locked_request,
                    resolution_type=(
                        resolution_type
                    ),
                    outcome_reason=(
                        outcome_reason
                    ),
                    legal_basis=legal_basis,
                    resolution_details_encrypted=(
                        encrypted_details
                    ),
                    encryption_key_version=(
                        key_version
                    ),
                    resolved_by=actor,
                    resolved_at=db_now,
                )
            )

            target_status = (
                cls.RESOLUTION_STATUS
                .get(resolution_type)
            )

            if target_status is not None:
                CaseWorkflowService \
                    ._record_status_change(
                        request=locked_request,
                        target_status=(
                            target_status
                        ),
                        actor=actor,
                        correlation_id=(
                            correlation_id
                        ),
                        trigger=(
                            "RESOLUTION_CREATED"
                        ),
                    )

            if (
                resolution_type
                in {
                    RequestResolution
                    .ResolutionType
                    .REJECTED,
                    RequestResolution
                    .ResolutionType
                    .ARCHIVED,
                    RequestResolution
                    .ResolutionType
                    .CANCELLED,
                }
            ):
                DeadlineService \
                    .complete_current(
                        request=locked_request,
                        actor=actor,
                        correlation_id=(
                            correlation_id
                        ),
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
                    "REQUEST_RESOLUTION_CREATED"
                ),
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                entity_pk=(
                    locked_request.id
                ),
                description=(
                    "Request resolution "
                    "created."
                ),
                metadata={
                    "reference_number": (
                        locked_request
                        .reference_number
                    ),
                    "resolution_type": (
                        resolution_type
                    ),
                    "outcome_reason_code": (
                        outcome_reason.code
                        if (
                            outcome_reason
                            is not None
                        )
                        else None
                    ),
                    "legal_basis_present": (
                        legal_basis
                        is not None
                    ),
                },
            )

            return resolution

    @classmethod
    def approve(
        cls,
        *,
        request: RightsRequest,
        details: str,
        actor,
        legal_basis: str | None = None,
        correlation_id=None,
    ) -> RequestResolution:
        return cls.resolve(
            request=request,
            resolution_type=(
                RequestResolution
                .ResolutionType
                .APPROVED
            ),
            details=details,
            actor=actor,
            legal_basis=legal_basis,
            correlation_id=correlation_id,
        )

    @classmethod
    def partially_approve(
        cls,
        *,
        request: RightsRequest,
        details: str,
        actor,
        legal_basis: str | None = None,
        correlation_id=None,
    ) -> RequestResolution:
        return cls.resolve(
            request=request,
            resolution_type=(
                RequestResolution
                .ResolutionType
                .PARTIALLY_APPROVED
            ),
            details=details,
            actor=actor,
            legal_basis=legal_basis,
            correlation_id=correlation_id,
        )

    @classmethod
    def reject(
        cls,
        *,
        request: RightsRequest,
        details: str,
        outcome_reason: CaseOutcomeReason,
        actor,
        legal_basis: str | None = None,
        correlation_id=None,
    ) -> RequestResolution:
        return cls.resolve(
            request=request,
            resolution_type=(
                RequestResolution
                .ResolutionType
                .REJECTED
            ),
            details=details,
            actor=actor,
            outcome_reason=outcome_reason,
            legal_basis=legal_basis,
            correlation_id=correlation_id,
        )

    @classmethod
    def archive(
        cls,
        *,
        request: RightsRequest,
        details: str,
        outcome_reason: CaseOutcomeReason,
        actor,
        legal_basis: str | None = None,
        correlation_id=None,
    ) -> RequestResolution:
        return cls.resolve(
            request=request,
            resolution_type=(
                RequestResolution
                .ResolutionType
                .ARCHIVED
            ),
            details=details,
            actor=actor,
            outcome_reason=outcome_reason,
            legal_basis=legal_basis,
            correlation_id=correlation_id,
        )

    @classmethod
    def cancel(
        cls,
        *,
        request: RightsRequest,
        details: str,
        outcome_reason: CaseOutcomeReason,
        actor,
        legal_basis: str | None = None,
        correlation_id=None,
    ) -> RequestResolution:
        return cls.resolve(
            request=request,
            resolution_type=(
                RequestResolution
                .ResolutionType
                .CANCELLED
            ),
            details=details,
            actor=actor,
            outcome_reason=outcome_reason,
            legal_basis=legal_basis,
            correlation_id=correlation_id,
        )

    @classmethod
    def mark_responded(
        cls,
        *,
        request: RightsRequest,
        actor,
        correlation_id=None,
    ) -> RightsRequest:
        actor = cls._validate_manager(
            actor
        )

        correlation_id = (
            cls._normalize_correlation_id(
                correlation_id
            )
        )

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .get(pk=request.pk)
            )

            resolution = (
                RequestResolution.objects
                .filter(
                    request=locked_request
                )
                .first()
            )

            if resolution is None:
                raise ResolutionConflictError(
                    "A resolution is required "
                    "before responding."
                )

            if (
                resolution.resolution_type
                not in {
                    RequestResolution
                    .ResolutionType
                    .APPROVED,
                    RequestResolution
                    .ResolutionType
                    .PARTIALLY_APPROVED,
                }
            ):
                raise ResolutionStateError(
                    "Only approved or partially "
                    "approved requests can be "
                    "marked RESPONDED."
                )

            allowed_statuses = {
                RightsRequest.Status.UNDER_REVIEW,
                RightsRequest.Status.EXTENDED,
                RightsRequest
                .Status
                .PARTIALLY_APPROVED,
            }

            if (
                locked_request.status
                not in allowed_statuses
            ):
                raise CaseTransitionError(
                    request_id=(
                        locked_request.id
                    ),
                    current_status=(
                        locked_request.status
                    ),
                    target_status=(
                        RightsRequest
                        .Status
                        .RESPONDED
                    ),
                )

            DeadlineService.complete_current(
                request=locked_request,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
            )

            CaseWorkflowService \
                ._record_status_change(
                    request=locked_request,
                    target_status=(
                        RightsRequest
                        .Status
                        .RESPONDED
                    ),
                    actor=actor,
                    correlation_id=(
                        correlation_id
                    ),
                    trigger=(
                        "RESPONSE_CONFIRMED"
                    ),
                )

            db_now = (
                CaseWorkflowService
                ._database_now()
            )

            locked_request.responded_at = (
                db_now
            )
            locked_request.current_due_at = (
                None
            )
            locked_request.updated_at = (
                db_now
            )
            locked_request.save(
                update_fields=[
                    "responded_at",
                    "current_due_at",
                    "updated_at",
                ]
            )

            return locked_request

    @classmethod
    def close(
        cls,
        *,
        request: RightsRequest,
        actor,
        correlation_id=None,
    ) -> RightsRequest:
        actor = cls._validate_manager(
            actor
        )

        correlation_id = (
            cls._normalize_correlation_id(
                correlation_id
            )
        )

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .get(pk=request.pk)
            )

            if not (
                RequestResolution.objects
                .filter(
                    request=locked_request
                )
                .exists()
            ):
                raise ResolutionConflictError(
                    "A resolution is required "
                    "before closing."
                )

            if (
                locked_request.status
                not in {
                    RightsRequest
                    .Status
                    .RESPONDED,
                    RightsRequest
                    .Status
                    .REJECTED,
                    RightsRequest
                    .Status
                    .ARCHIVED,
                    RightsRequest
                    .Status
                    .CANCELLED,
                }
            ):
                raise ResolutionStateError(
                    "Request is not in a "
                    "closable state."
                )

            open_clarification = (
                RequestClarification.objects
                .filter(
                    request=locked_request,
                    status=(
                        RequestClarification
                        .Status
                        .REQUESTED
                    ),
                )
                .exists()
            )

            if open_clarification:
                raise (
                    ResolutionCloseBlockedError(
                        "Open clarification "
                        "blocks closure."
                    )
                )

            open_deadline = (
                RequestDeadline.objects
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
                .exists()
            )

            if open_deadline:
                raise (
                    ResolutionCloseBlockedError(
                        "Open deadline "
                        "blocks closure."
                    )
                )

            CaseWorkflowService \
                ._record_status_change(
                    request=locked_request,
                    target_status=(
                        RightsRequest
                        .Status
                        .CLOSED
                    ),
                    actor=actor,
                    correlation_id=(
                        correlation_id
                    ),
                    trigger=(
                        "CASE_CLOSED"
                    ),
                )

            db_now = (
                CaseWorkflowService
                ._database_now()
            )

            locked_request.closed_at = (
                db_now
            )
            locked_request.current_due_at = (
                None
            )
            locked_request.updated_at = (
                db_now
            )
            locked_request.save(
                update_fields=[
                    "closed_at",
                    "current_due_at",
                    "updated_at",
                ]
            )

            return locked_request

    @classmethod
    def decrypt_details(
        cls,
        resolution: RequestResolution,
    ) -> str:
        return CryptoService.decrypt_text(
            resolution
            .resolution_details_encrypted,
            aad=(
                "request_resolutions:"
                f"{resolution.id}:"
                "resolution_details"
            ),
            key_version=(
                resolution
                .encryption_key_version
            ),
        )
