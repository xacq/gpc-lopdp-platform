from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hmac
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

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
from apps.communications.models import RequestCommunication
from apps.communications.services.notifications import NotificationService
from apps.core.services.crypto import CryptoService
from apps.organization.models import SystemSetting
from apps.subjects.services.normalization import normalize_email


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


class PublicTrackingCodeResendError(PublicTrackingError):
    """Generic error for the public tracking-code recovery flow."""

    pass


@dataclass(frozen=True)
class PublicTrackingHistoryItem:
    status: str
    changed_at: datetime


@dataclass(frozen=True)
class PublicTrackingResult:
    reference_number: str
    right_name: str
    status: str
    received_at: datetime
    current_due_at: datetime | None
    responded_at: datetime | None
    closed_at: datetime | None
    history: tuple[
        PublicTrackingHistoryItem,
        ...
    ]


@dataclass(frozen=True)
class PublicTrackingCodeResendResult:
    queued: bool


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
                .select_related("right")
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
                right_name=request.right.name,
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


class PublicTrackingCodeResendService:
    DEFAULT_COOLDOWN_SECONDS = 5 * 60

    @classmethod
    def _cooldown_seconds(cls) -> int:
        seconds = int(
            getattr(
                settings,
                "PUBLIC_TRACKING_RESEND_COOLDOWN_SECONDS",
                cls.DEFAULT_COOLDOWN_SECONDS,
            )
        )
        if seconds <= 0:
            raise PublicTrackingCodeResendError()
        return seconds

    @classmethod
    def _normalize_reference(cls, reference_number: str) -> str:
        if not isinstance(reference_number, str):
            raise PublicTrackingCodeResendError()
        reference_number = reference_number.strip().upper()
        if not reference_number:
            raise PublicTrackingCodeResendError()
        return reference_number

    @classmethod
    def resend(
        cls,
        *,
        reference_number: str,
        email: str,
        correlation_id=None,
    ) -> PublicTrackingCodeResendResult:
        reference_number = cls._normalize_reference(reference_number)
        try:
            email = normalize_email(email)
        except (TypeError, ValueError) as exc:
            raise PublicTrackingCodeResendError() from exc

        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(correlation_id, uuid.UUID):
            correlation_id = uuid.UUID(str(correlation_id))

        with transaction.atomic():
            request = (
                RightsRequest.objects.select_for_update()
                .select_related("data_subject")
                .filter(reference_number=reference_number)
                .first()
            )
            if request is None:
                return PublicTrackingCodeResendResult(queued=False)

            subject = request.data_subject
            supplied_email_hash = CryptoService.lookup_hash(
                f"email:{email}",
                key_version=subject.lookup_key_version,
            ).value
            if not hmac.compare_digest(
                supplied_email_hash,
                subject.email_lookup_hash,
            ):
                return PublicTrackingCodeResendResult(queued=False)

            cooldown = timedelta(seconds=cls._cooldown_seconds())
            latest_token = (
                request.access_tokens.filter(
                    purpose=RequestAccessToken.Purpose.TRACKING
                )
                .order_by("-created_at")
                .first()
            )
            if (
                latest_token is not None
                and latest_token.created_at >= timezone.now() - cooldown
            ):
                return PublicTrackingCodeResendResult(queued=False)

            tracking_ttl = cls._tracking_ttl()
            tracking = RequestAccessTokenService.issue(
                request=request,
                purpose=RequestAccessToken.Purpose.TRACKING,
                ttl=tracking_ttl,
                correlation_id=correlation_id,
                source=AuditLog.Source.WEB,
            )
            organization = SystemSetting.objects.get(singleton_key=1)
            public_site_url = settings.PUBLIC_SITE_URL or (
                f"https://{organization.domain}"
            )
            tracking_url = (
                f"{public_site_url.rstrip('/')}/cases/public/tracking/"
            )
            NotificationService.queue_email(
                request=request,
                communication_type=(
                    RequestCommunication.CommunicationType.ACKNOWLEDGEMENT
                ),
                recipient=email,
                subject=(
                    f"Código de seguimiento: {request.reference_number}"
                ),
                body=(
                    "Solicitaste un nuevo código para consultar tu solicitud.\n\n"
                    f"Referencia: {request.reference_number}\n"
                    f"Consulta el estado en: {tracking_url}\n"
                    f"Código de seguimiento: {tracking.token}\n\n"
                    "No compartas este código con terceros."
                ),
                visible_to_subject=False,
                actor=None,
                correlation_id=correlation_id,
            )
            AuditService.write(
                actor_type=AuditLog.ActorType.SYSTEM,
                actor=None,
                source=AuditLog.Source.WEB,
                correlation_id=correlation_id,
                action="PUBLIC_TRACKING_CODE_REISSUED",
                entity_type="RIGHTS_REQUEST",
                entity_pk=request.id,
                description="Public tracking access code reissued.",
                metadata={"request_id": str(request.id)},
            )

        return PublicTrackingCodeResendResult(queued=True)

    @classmethod
    def _tracking_ttl(cls):
        seconds = int(
            getattr(
                settings,
                "PUBLIC_TRACKING_TTL_SECONDS",
                90 * 24 * 60 * 60,
            )
        )
        if seconds <= 0:
            raise PublicTrackingCodeResendError()
        return timedelta(seconds=seconds)
