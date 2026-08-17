from __future__ import annotations

import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import (
    RequestAccessToken,
    RightsRequest,
)
from apps.core.services.crypto import CryptoService


class RequestAccessTokenServiceError(Exception):
    pass


class TokenConfigurationError(
    RequestAccessTokenServiceError
):
    pass


class TokenBindingError(
    RequestAccessTokenServiceError
):
    pass


class TokenInvalidOrExpiredError(
    RequestAccessTokenServiceError
):
    """
    Deliberately generic public-facing domain error.

    Do not distinguish invalid token, missing token,
    expired token, revoked token, or temporary lockout
    at the endpoint layer.
    """

    pass


@dataclass(frozen=True)
class IssuedRequestAccessToken:
    record: RequestAccessToken
    token: str


class RequestAccessTokenService:
    TOKEN_BYTES = 32

    DEFAULT_MAX_FAILED_ATTEMPTS = 5
    DEFAULT_LOCK_MINUTES = 15

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
    def _normalize_purpose(
        cls,
        purpose: str,
    ) -> str:
        purpose = purpose.strip().upper()

        valid = {
            choice[0]
            for choice in (
                RequestAccessToken
                .Purpose
                .choices
            )
        }

        if purpose not in valid:
            raise ValueError(
                f"Invalid token purpose: "
                f"{purpose}"
            )

        return purpose

    @classmethod
    def _normalize_resource_binding(
        cls,
        *,
        purpose: str,
        resource_type: str | None,
        resource_id,
    ) -> tuple[str | None, uuid.UUID | None]:
        if (
            resource_type is not None
            and resource_type.strip()
        ):
            resource_type = (
                resource_type
                .strip()
                .upper()
            )
        else:
            resource_type = None

        if resource_id is not None:
            if not isinstance(
                resource_id,
                uuid.UUID,
            ):
                try:
                    resource_id = uuid.UUID(
                        str(resource_id)
                    )
                except (
                    TypeError,
                    ValueError,
                    AttributeError,
                ) as exc:
                    raise TokenBindingError(
                        "Invalid resource binding."
                    ) from exc

        if (
            purpose
            == RequestAccessToken
            .Purpose
            .FILE_DOWNLOAD
        ):
            if (
                resource_type
                != RequestAccessToken
                .ResourceType
                .ATTACHMENT
                or resource_id is None
            ):
                raise TokenBindingError(
                    "Invalid resource binding."
                )

            return (
                resource_type,
                resource_id,
            )

        if (
            purpose
            == RequestAccessToken
            .Purpose
            .PORTABILITY_DOWNLOAD
        ):
            if (
                resource_type
                != RequestAccessToken
                .ResourceType
                .PORTABILITY_EXPORT
                or resource_id is None
            ):
                raise TokenBindingError(
                    "Invalid resource binding."
                )

            return (
                resource_type,
                resource_id,
            )

        if purpose in {
            RequestAccessToken
            .Purpose
            .TRACKING,
            RequestAccessToken
            .Purpose
            .EMAIL_VERIFICATION,
        }:
            if (
                resource_type is not None
                or resource_id is not None
            ):
                raise TokenBindingError(
                    "Invalid resource binding."
                )

            return None, None

        raise TokenBindingError(
            "Invalid resource binding."
        )

    @classmethod
    def _token_material(
        cls,
        *,
        request_id: uuid.UUID,
        purpose: str,
        resource_type: str | None,
        resource_id: uuid.UUID | None,
        token: str,
    ) -> str:
        return (
            "request_access_token:"
            f"{request_id}:"
            f"{purpose}:"
            f"{resource_type or '-'}:"
            f"{resource_id or '-'}:"
            f"{token}"
        )

    @classmethod
    def _hash_token(
        cls,
        *,
        request_id: uuid.UUID,
        purpose: str,
        resource_type: str | None,
        resource_id: uuid.UUID | None,
        token: str,
        key_version: int,
    ) -> str:
        digest = CryptoService.lookup_hash(
            cls._token_material(
                request_id=request_id,
                purpose=purpose,
                resource_type=resource_type,
                resource_id=resource_id,
                token=token,
            ),
            key_version=key_version,
        )

        return digest.value

    @classmethod
    def _scope_queryset(
        cls,
        *,
        request: RightsRequest,
        purpose: str,
        resource_type: str | None,
        resource_id: uuid.UUID | None,
    ):
        return (
            RequestAccessToken.objects
            .filter(
                request=request,
                purpose=purpose,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )

    @classmethod
    def _max_failed_attempts(
        cls,
    ) -> int:
        value = int(
            getattr(
                settings,
                "ACCESS_TOKEN_MAX_FAILED_ATTEMPTS",
                cls.DEFAULT_MAX_FAILED_ATTEMPTS,
            )
        )

        if value <= 0:
            raise TokenConfigurationError(
                "ACCESS_TOKEN_MAX_FAILED_ATTEMPTS "
                "must be greater than zero."
            )

        return value

    @classmethod
    def _lock_duration(
        cls,
    ) -> timedelta:
        minutes = int(
            getattr(
                settings,
                "ACCESS_TOKEN_LOCK_MINUTES",
                cls.DEFAULT_LOCK_MINUTES,
            )
        )

        if minutes <= 0:
            raise TokenConfigurationError(
                "ACCESS_TOKEN_LOCK_MINUTES "
                "must be greater than zero."
            )

        return timedelta(
            minutes=minutes
        )

    @classmethod
    def _audit(
        cls,
        *,
        action: str,
        record: RequestAccessToken,
        actor=None,
        correlation_id: uuid.UUID | None = None,
        source: str | None = None,
    ):
        actor_type = (
            AuditLog.ActorType.USER
            if actor is not None
            else AuditLog.ActorType.SYSTEM
        )

        if source is None:
            source = (
                AuditLog.Source.WEB
                if actor is not None
                else AuditLog.Source.SYSTEM
            )

        AuditService.write(
            actor_type=actor_type,
            actor=actor,
            source=source,
            correlation_id=correlation_id,
            action=action,
            entity_type=(
                "REQUEST_ACCESS_TOKEN"
            ),
            entity_pk=record.id,
            description=(
                "Request access token "
                "security event."
            ),
            metadata={
                "request_id": str(
                    record.request_id
                ),
                "purpose": record.purpose,
                "resource_type": (
                    record.resource_type
                ),
                "resource_id": (
                    str(record.resource_id)
                    if (
                        record.resource_id
                        is not None
                    )
                    else None
                ),
            },
        )

    @classmethod
    def issue(
        cls,
        *,
        request: RightsRequest,
        purpose: str,
        ttl: timedelta,
        resource_type: str | None = None,
        resource_id=None,
        actor=None,
        correlation_id: uuid.UUID | None = None,
        source: str | None = None,
    ) -> IssuedRequestAccessToken:
        purpose = cls._normalize_purpose(
            purpose
        )

        (
            resource_type,
            resource_id,
        ) = cls._normalize_resource_binding(
            purpose=purpose,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        if (
            not isinstance(ttl, timedelta)
            or ttl <= timedelta(0)
        ):
            raise ValueError(
                "ttl must be a positive "
                "datetime.timedelta."
            )

        lookup_version = int(
            settings
            .LOOKUP_HMAC_ACTIVE_VERSION
        )

        configured_keys = getattr(
            settings,
            "LOOKUP_HMAC_KEYS",
            {},
        )

        if not configured_keys.get(
            lookup_version
        ):
            raise TokenConfigurationError(
                "Active lookup HMAC key "
                "is not configured."
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

            db_now = cls._database_now()

            active_scope = (
                cls._scope_queryset(
                    request=locked_request,
                    purpose=purpose,
                    resource_type=(
                        resource_type
                    ),
                    resource_id=resource_id,
                )
                .select_for_update()
                .filter(
                    revoked_at__isnull=True
                )
            )

            active_scope.update(
                revoked_at=db_now
            )

            raw_token = (
                secrets.token_urlsafe(
                    cls.TOKEN_BYTES
                )
            )

            token_hash = cls._hash_token(
                request_id=(
                    locked_request.id
                ),
                purpose=purpose,
                resource_type=resource_type,
                resource_id=resource_id,
                token=raw_token,
                key_version=lookup_version,
            )

            record = (
                RequestAccessToken.objects
                .create(
                    request=locked_request,
                    token_hash=token_hash,
                    lookup_key_version=(
                        lookup_version
                    ),
                    purpose=purpose,
                    resource_type=(
                        resource_type
                    ),
                    resource_id=resource_id,
                    expires_at=(
                        db_now + ttl
                    ),
                    failed_attempts=0,
                )
            )

            cls._audit(
                action=(
                    "REQUEST_ACCESS_TOKEN_ISSUED"
                ),
                record=record,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
                source=source,
            )

            return IssuedRequestAccessToken(
                record=record,
                token=raw_token,
            )

    @classmethod
    def validate(
        cls,
        *,
        request: RightsRequest,
        token: str,
        purpose: str,
        resource_type: str | None = None,
        resource_id=None,
    ) -> RequestAccessToken:
        purpose = cls._normalize_purpose(
            purpose
        )

        (
            resource_type,
            resource_id,
        ) = cls._normalize_resource_binding(
            purpose=purpose,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        token = (
            token.strip()
            if isinstance(token, str)
            else ""
        )

        if not token:
            raise (
                TokenInvalidOrExpiredError()
            )

        with transaction.atomic():
            locked_request = (
                RightsRequest.objects
                .select_for_update()
                .get(pk=request.pk)
            )

            candidate = (
                cls._scope_queryset(
                    request=locked_request,
                    purpose=purpose,
                    resource_type=(
                        resource_type
                    ),
                    resource_id=resource_id,
                )
                .select_for_update()
                .filter(
                    revoked_at__isnull=True
                )
                .order_by(
                    "-created_at",
                    "-id",
                )
                .first()
            )

            if candidate is None:
                raise (
                    TokenInvalidOrExpiredError()
                )

            db_now = cls._database_now()

            if (
                candidate.expires_at
                <= db_now
            ):
                raise (
                    TokenInvalidOrExpiredError()
                )

            if (
                candidate.locked_until
                is not None
                and candidate.locked_until
                > db_now
            ):
                raise (
                    TokenInvalidOrExpiredError()
                )

            if (
                candidate.locked_until
                is not None
                and candidate.locked_until
                <= db_now
            ):
                candidate.failed_attempts = 0
                candidate.locked_until = None

            try:
                presented_hash = (
                    cls._hash_token(
                        request_id=(
                            locked_request.id
                        ),
                        purpose=purpose,
                        resource_type=(
                            resource_type
                        ),
                        resource_id=(
                            resource_id
                        ),
                        token=token,
                        key_version=(
                            candidate
                            .lookup_key_version
                        ),
                    )
                )
            except Exception as exc:
                raise (
                    TokenConfigurationError(
                        "Lookup HMAC key "
                        "configuration error."
                    )
                ) from exc

            if not hmac.compare_digest(
                candidate.token_hash,
                presented_hash,
            ):
                candidate.failed_attempts += 1

                update_fields = [
                    "failed_attempts",
                ]

                if (
                    candidate.failed_attempts
                    >= cls._max_failed_attempts()
                ):
                    candidate.locked_until = (
                        db_now
                        + cls._lock_duration()
                    )
                    update_fields.append(
                        "locked_until"
                    )

                candidate.save(
                    update_fields=(
                        update_fields
                    )
                )

                invalid_token = True

            else:
                candidate.failed_attempts = 0
                candidate.locked_until = None
                candidate.last_used_at = db_now

                candidate.save(
                    update_fields=[
                        "failed_attempts",
                        "locked_until",
                        "last_used_at",
                    ]
                )

                invalid_token = False

        if invalid_token:
            raise (
                TokenInvalidOrExpiredError()
            )

        return candidate

    @classmethod
    def consume(
        cls,
        *,
        request: RightsRequest,
        token: str,
        purpose: str,
        resource_type: str | None = None,
        resource_id=None,
        actor=None,
        correlation_id: uuid.UUID | None = None,
        source: str | None = None,
    ) -> RequestAccessToken:
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
            record = cls.validate(
                request=request,
                token=token,
                purpose=purpose,
                resource_type=(
                    resource_type
                ),
                resource_id=resource_id,
            )

            db_now = cls._database_now()

            record.revoked_at = db_now
            record.save(
                update_fields=[
                    "revoked_at",
                ]
            )

            cls._audit(
                action=(
                    "REQUEST_ACCESS_TOKEN_CONSUMED"
                ),
                record=record,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
                source=source,
            )

            return record

    @classmethod
    def revoke(
        cls,
        *,
        access_token: RequestAccessToken,
        actor=None,
        correlation_id: uuid.UUID | None = None,
        source: str | None = None,
    ) -> RequestAccessToken:
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
            record = (
                RequestAccessToken.objects
                .select_for_update()
                .get(pk=access_token.pk)
            )

            if record.revoked_at is not None:
                return record

            record.revoked_at = (
                cls._database_now()
            )

            record.save(
                update_fields=[
                    "revoked_at",
                ]
            )

            cls._audit(
                action=(
                    "REQUEST_ACCESS_TOKEN_REVOKED"
                ),
                record=record,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
                source=source,
            )

            return record

    @classmethod
    def is_expired(
        cls,
        access_token: RequestAccessToken,
    ) -> bool:
        return (
            access_token.expires_at
            <= cls._database_now()
        )
