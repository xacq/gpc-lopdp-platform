from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import uuid

from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import (
    RequestAccessToken,
    RequestStatusHistory,
    RightsRequest,
)
from apps.cases.services.tokens import (
    RequestAccessTokenService,
    TokenInvalidOrExpiredError,
)


class PublicTrackingError(Exception):
    pass


class PublicTrackingAccessError(
    PublicTrackingError
):
    """
    Generic public-facing access error.

    Do not distinguish an unknown reference from
    an invalid, expired, revoked, or locked token.
    """

    pass


@dataclass(frozen=True)
class PublicTrackingHistoryItem:
    status: str
    changed_at: datetime


@dataclass(frozen=True)
class PublicTrackingResult:
    reference_number: str
    status: str
    received_at: datetime
    current_due_at: datetime | None
    responded_at: datetime | None
    closed_at: datetime | None
    history: tuple[
        PublicTrackingHistoryItem,
        ...
    ]


class PublicTrackingService:
    @classmethod
    def _normalize_reference(
        cls,
        reference_number: str,
    ) -> str:
        if not isinstance(
            reference_number,
            str,
        ):
            raise PublicTrackingAccessError()

        reference_number = (
            reference_number
            .strip()
            .upper()
        )

        if not reference_number:
            raise PublicTrackingAccessError()

        return reference_number

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
    def _history(
        cls,
        request: RightsRequest,
    ) -> tuple[
        PublicTrackingHistoryItem,
        ...
    ]:
        rows = (
            RequestStatusHistory.objects
            .filter(
                request=request
            )
            .values(
                "new_status",
                "changed_at",
            )
            .order_by(
                "changed_at",
                "id",
            )
        )

        return tuple(
            PublicTrackingHistoryItem(
                status=row["new_status"],
                changed_at=row["changed_at"],
            )
            for row in rows
        )

    @classmethod
    def get_status(
        cls,
        *,
        reference_number: str,
        token: str,
        correlation_id=None,
    ) -> PublicTrackingResult:
        reference_number = (
            cls._normalize_reference(
                reference_number
            )
        )

        correlation_id = (
            cls._normalize_correlation_id(
                correlation_id
            )
        )

        with transaction.atomic():
            request = (
                RightsRequest.objects
                .filter(
                    reference_number=(
                        reference_number
                    )
                )
                .first()
            )

            if request is None:
                raise PublicTrackingAccessError()

            try:
                (
                    RequestAccessTokenService
                    .validate(
                        request=request,
                        token=token,
                        purpose=(
                            RequestAccessToken
                            .Purpose
                            .TRACKING
                        ),
                    )
                )
            except (
                TokenInvalidOrExpiredError
            ) as exc:
                raise PublicTrackingAccessError() from exc

            result = PublicTrackingResult(
                reference_number=(
                    request.reference_number
                ),
                status=request.status,
                received_at=(
                    request.received_at
                ),
                current_due_at=(
                    request.current_due_at
                ),
                responded_at=(
                    request.responded_at
                ),
                closed_at=(
                    request.closed_at
                ),
                history=cls._history(
                    request
                ),
            )

            AuditService.write(
                actor_type=(
                    AuditLog.ActorType.SYSTEM
                ),
                actor=None,
                source=AuditLog.Source.WEB,
                correlation_id=(
                    correlation_id
                ),
                action=(
                    "PUBLIC_TRACKING_ACCESSED"
                ),
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                entity_pk=request.id,
                description=(
                    "Public request tracking "
                    "status accessed."
                ),
                metadata={
                    "reference_number": (
                        request
                        .reference_number
                    ),
                    "status": (
                        request.status
                    ),
                },
            )

            return result
