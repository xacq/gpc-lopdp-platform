from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Callable

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError, connection, transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.communications.models import RequestCommunication
from apps.core.services.crypto import CryptoService


class NotificationServiceError(Exception):
    pass


class CommunicationStateError(
    NotificationServiceError
):
    pass


class CommunicationPayloadError(
    NotificationServiceError
):
    pass


class NotificationService:
    DEFAULT_MAX_ATTEMPTS = 5
    DEFAULT_RETRY_MINUTES = 5
    MAX_RETRY_MINUTES = 60

    EMAIL_PATTERN = re.compile(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        re.IGNORECASE,
    )

    @classmethod
    def _database_now(cls):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT transaction_timestamp()"
            )
            row = cursor.fetchone()

        return row[0]

    @classmethod
    def _normalize_text(
        cls,
        value: str,
        *,
        field_name: str,
        max_length: int | None = None,
    ) -> str:
        if not isinstance(value, str):
            raise CommunicationPayloadError(
                f"{field_name} must be text."
            )

        value = value.strip()

        if not value:
            raise CommunicationPayloadError(
                f"{field_name} is required."
            )

        if (
            max_length is not None
            and len(value) > max_length
        ):
            raise CommunicationPayloadError(
                f"{field_name} exceeds "
                f"{max_length} characters."
            )

        return value

    @classmethod
    def _validate_choice(
        cls,
        *,
        field_name: str,
        value: str,
    ) -> str:
        value = value.strip().upper()

        field = (
            RequestCommunication
            ._meta
            .get_field(field_name)
        )

        valid = {
            choice[0]
            for choice in field.choices
        }

        if value not in valid:
            raise ValueError(
                f"Invalid {field_name}: {value}"
            )

        return value

    @classmethod
    def _aad(
        cls,
        communication_id: uuid.UUID,
        field_name: str,
    ) -> bytes:
        return (
            "request_communications:"
            f"{communication_id}:"
            f"{field_name}"
        ).encode("utf-8")

    @classmethod
    def _encrypt_text(
        cls,
        *,
        communication_id: uuid.UUID,
        field_name: str,
        value: str,
        key_version: int,
    ) -> bytes:
        encrypted = CryptoService.encrypt_text(
            value,
            aad=cls._aad(
                communication_id,
                field_name,
            ),
            key_version=key_version,
        )

        return encrypted.data

    @classmethod
    def _decrypt_text(
        cls,
        *,
        communication: RequestCommunication,
        field_name: str,
        value: bytes | None,
    ) -> str | None:
        if not value:
            return None

        return CryptoService.decrypt_text(
            value,
            aad=cls._aad(
                communication.id,
                field_name,
            ),
            key_version=(
                communication
                .encryption_key_version
            ),
        )

    @classmethod
    def _max_attempts(cls) -> int:
        value = int(
            getattr(
                settings,
                "COMMUNICATION_MAX_ATTEMPTS",
                cls.DEFAULT_MAX_ATTEMPTS,
            )
        )

        if value <= 0:
            raise NotificationServiceError(
                "COMMUNICATION_MAX_ATTEMPTS "
                "must be greater than zero."
            )

        return value

    @classmethod
    def _retry_delay(
        cls,
        attempt_count: int,
    ) -> timedelta:
        base = int(
            getattr(
                settings,
                "COMMUNICATION_RETRY_MINUTES",
                cls.DEFAULT_RETRY_MINUTES,
            )
        )

        if base <= 0:
            raise NotificationServiceError(
                "COMMUNICATION_RETRY_MINUTES "
                "must be greater than zero."
            )

        minutes = min(
            base * (2 ** max(
                attempt_count - 1,
                0,
            )),
            cls.MAX_RETRY_MINUTES,
        )

        return timedelta(
            minutes=minutes
        )

    @classmethod
    def _sanitize_error(
        cls,
        exc: Exception,
    ) -> str:
        error_class = (
            exc.__class__.__name__
        )

        value = (
            "EMAIL_DELIVERY_FAILED:"
            f"{error_class}"
        )

        value = cls.EMAIL_PATTERN.sub(
            "[REDACTED_EMAIL]",
            value,
        )

        return value[:500]

    @classmethod
    def _audit(
        cls,
        *,
        action: str,
        communication: RequestCommunication,
        correlation_id: uuid.UUID,
        actor=None,
        source: str = AuditLog.Source.SYSTEM,
    ) -> None:
        AuditService.write(
            actor_type=(
                AuditLog.ActorType.USER
                if actor is not None
                else AuditLog.ActorType.SYSTEM
            ),
            actor=actor,
            source=source,
            correlation_id=correlation_id,
            action=action,
            entity_type=(
                "REQUEST_COMMUNICATION"
            ),
            entity_pk=communication.id,
            description=(
                "Request communication "
                "processing event."
            ),
            metadata={
                "request_id": str(
                    communication.request_id
                ),
                "communication_type": (
                    communication
                    .communication_type
                ),
                "channel": (
                    communication.channel
                ),
                "delivery_status": (
                    communication
                    .delivery_status
                ),
                "attempt_count": (
                    communication
                    .attempt_count
                ),
            },
        )

    @classmethod
    def queue_email(
        cls,
        *,
        request,
        communication_type: str,
        recipient: str,
        subject: str,
        body: str,
        visible_to_subject: bool,
        actor=None,
        idempotency_key: (
            uuid.UUID | None
        ) = None,
        correlation_id: (
            uuid.UUID | None
        ) = None,
        enqueue_callback: (
            Callable[[uuid.UUID], None]
            | None
        ) = None,
    ) -> RequestCommunication:
        communication_type = (
            cls._validate_choice(
                field_name=(
                    "communication_type"
                ),
                value=communication_type,
            )
        )

        recipient = cls._normalize_text(
            recipient,
            field_name="recipient",
            max_length=254,
        )
        subject = cls._normalize_text(
            subject,
            field_name="subject",
            max_length=998,
        )
        body = cls._normalize_text(
            body,
            field_name="body",
        )

        if idempotency_key is None:
            idempotency_key = uuid.uuid4()
        elif not isinstance(
            idempotency_key,
            uuid.UUID,
        ):
            idempotency_key = uuid.UUID(
                str(idempotency_key)
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

        existing = (
            RequestCommunication.objects
            .filter(
                idempotency_key=(
                    idempotency_key
                )
            )
            .first()
        )

        if existing is not None:
            return existing

        communication_id = uuid.uuid4()
        key_version = int(
            settings
            .PII_ENCRYPTION_ACTIVE_VERSION
        )

        recipient_encrypted = (
            cls._encrypt_text(
                communication_id=(
                    communication_id
                ),
                field_name="recipient",
                value=recipient,
                key_version=key_version,
            )
        )

        subject_encrypted = (
            cls._encrypt_text(
                communication_id=(
                    communication_id
                ),
                field_name="subject",
                value=subject,
                key_version=key_version,
            )
        )

        body_encrypted = (
            cls._encrypt_text(
                communication_id=(
                    communication_id
                ),
                field_name="body",
                value=body,
                key_version=key_version,
            )
        )

        with transaction.atomic():
            try:
                with transaction.atomic():
                    communication = (
                        RequestCommunication.objects
                        .create(
                            id=communication_id,
                            request=request,
                            direction="OUTBOUND",
                            channel="EMAIL",
                            communication_type=(
                                communication_type
                            ),
                            visible_to_subject=(
                                visible_to_subject
                            ),
                            recipient_encrypted=(
                                recipient_encrypted
                            ),
                            subject_encrypted=(
                                subject_encrypted
                            ),
                            body_encrypted=(
                                body_encrypted
                            ),
                            encryption_key_version=(
                                key_version
                            ),
                            idempotency_key=(
                                idempotency_key
                            ),
                            delivery_status="PENDING",
                            attempt_count=0,
                        )
                    )
            except IntegrityError:
                existing = (
                    RequestCommunication.objects
                    .filter(
                        idempotency_key=(
                            idempotency_key
                        )
                    )
                    .first()
                )

                if existing is None:
                    raise

                return existing

            cls._audit(
                action=(
                    "REQUEST_COMMUNICATION_QUEUED"
                ),
                communication=communication,
                actor=actor,
                correlation_id=(
                    correlation_id
                ),
                source=(
                    AuditLog.Source.WEB
                    if actor is not None
                    else AuditLog.Source.SYSTEM
                ),
            )

            if enqueue_callback is not None:
                transaction.on_commit(
                    lambda: enqueue_callback(
                        communication.id
                    )
                )

            return communication

    @classmethod
    def decrypt_payload(
        cls,
        communication: RequestCommunication,
    ) -> dict[str, str | None]:
        return {
            "recipient": cls._decrypt_text(
                communication=communication,
                field_name="recipient",
                value=(
                    communication
                    .recipient_encrypted
                ),
            ),
            "subject": cls._decrypt_text(
                communication=communication,
                field_name="subject",
                value=(
                    communication
                    .subject_encrypted
                ),
            ),
            "body": cls._decrypt_text(
                communication=communication,
                field_name="body",
                value=(
                    communication
                    .body_encrypted
                ),
            ),
        }

    @classmethod
    def process_email(
        cls,
        communication_id,
        *,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> RequestCommunication:
        if not isinstance(
            communication_id,
            uuid.UUID,
        ):
            communication_id = uuid.UUID(
                str(communication_id)
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
            communication = (
                RequestCommunication.objects
                .select_for_update()
                .get(pk=communication_id)
            )

            if (
                communication
                .delivery_status
                in {
                    "SENT",
                    "DELIVERED",
                    "CANCELLED",
                }
            ):
                return communication

            if (
                communication.channel
                != "EMAIL"
                or communication.direction
                != "OUTBOUND"
            ):
                raise CommunicationStateError(
                    "Communication is not an "
                    "outbound email."
                )

            db_now = cls._database_now()

            if (
                communication.next_retry_at
                is not None
                and communication
                .next_retry_at
                > db_now
            ):
                raise CommunicationStateError(
                    "Communication is not due "
                    "for retry yet."
                )

            communication.delivery_status = (
                "PROCESSING"
            )
            communication.attempt_count += 1
            communication.last_attempt_at = (
                db_now
            )
            communication.next_retry_at = (
                None
            )
            communication.last_error = None

            communication.save(
                update_fields=[
                    "delivery_status",
                    "attempt_count",
                    "last_attempt_at",
                    "next_retry_at",
                    "last_error",
                ]
            )

            payload = cls.decrypt_payload(
                communication
            )

        try:
            message = EmailMessage(
                subject=payload["subject"],
                body=payload["body"],
                to=[payload["recipient"]],
            )

            sent_count = message.send(
                fail_silently=False
            )

            if sent_count != 1:
                raise RuntimeError(
                    "Email backend did not "
                    "confirm one message."
                )

        except Exception as exc:
            with transaction.atomic():
                communication = (
                    RequestCommunication.objects
                    .select_for_update()
                    .get(pk=communication_id)
                )

                db_now = cls._database_now()

                communication.delivery_status = (
                    "FAILED"
                )
                communication.last_error = (
                    cls._sanitize_error(exc)
                )

                if (
                    communication
                    .attempt_count
                    < cls._max_attempts()
                ):
                    communication.next_retry_at = (
                        db_now
                        + cls._retry_delay(
                            communication
                            .attempt_count
                        )
                    )
                else:
                    communication.next_retry_at = (
                        None
                    )

                communication.save(
                    update_fields=[
                        "delivery_status",
                        "last_error",
                        "next_retry_at",
                    ]
                )

                cls._audit(
                    action=(
                        "REQUEST_COMMUNICATION_FAILED"
                    ),
                    communication=(
                        communication
                    ),
                    correlation_id=(
                        correlation_id
                    ),
                    source=(
                        AuditLog.Source.CELERY
                    ),
                )

            return communication

        with transaction.atomic():
            communication = (
                RequestCommunication.objects
                .select_for_update()
                .get(pk=communication_id)
            )

            db_now = cls._database_now()

            communication.delivery_status = (
                "SENT"
            )
            communication.sent_at = db_now
            communication.next_retry_at = (
                None
            )
            communication.last_error = None

            communication.save(
                update_fields=[
                    "delivery_status",
                    "sent_at",
                    "next_retry_at",
                    "last_error",
                ]
            )

            cls._audit(
                action=(
                    "REQUEST_COMMUNICATION_SENT"
                ),
                communication=communication,
                correlation_id=(
                    correlation_id
                ),
                source=(
                    AuditLog.Source.CELERY
                ),
            )

            return communication
