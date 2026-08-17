from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction

from apps.audit.models import AuditLog
from apps.core.services.crypto import CryptoService


_REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "otp",
    "token",
    "authorization",
    "cookie",
    "session",
    "document_number",
    "document_encrypted",
    "cedula",
    "passport",
    "full_name",
    "first_name",
    "last_name",
    "representative_name",
    "email",
    "phone",
    "mobile",
    "address",
    "filename",
    "file_name",
    "payload",
    "request_body",
    "response_body",
)

_EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

_BEARER_RE = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+\b",
    re.IGNORECASE,
)


class AuditServiceError(Exception):
    pass


class AuditActorError(AuditServiceError):
    pass


class AuditChainIntegrityError(AuditServiceError):
    def __init__(
        self,
        *,
        chain_scope: str,
        chain_position: int | None,
        message: str,
    ):
        self.chain_scope = chain_scope
        self.chain_position = chain_position

        super().__init__(
            f"Audit chain integrity error "
            f"[{chain_scope}:{chain_position}]: "
            f"{message}"
        )


@dataclass(frozen=True)
class AuditChainVerificationResult:
    chain_scope: str
    checked_entries: int


class LogSanitizer:
    @classmethod
    def _is_sensitive_key(
        cls,
        key: str,
    ) -> bool:
        normalized = key.strip().lower()

        if normalized.endswith("_encrypted"):
            return True

        if normalized.endswith("_lookup_hash"):
            return True

        return any(
            part in normalized
            for part in _SENSITIVE_KEY_PARTS
        )

    @classmethod
    def _sanitize_string(
        cls,
        value: str,
    ) -> str:
        value = _EMAIL_RE.sub(
            _REDACTED,
            value,
        )

        value = _BEARER_RE.sub(
            _REDACTED,
            value,
        )

        return value

    @classmethod
    def sanitize(
        cls,
        value: Any,
    ) -> Any:
        if value is None:
            return None

        if isinstance(value, dict):
            sanitized = {}

            for key, item in value.items():
                key_text = str(key)

                if cls._is_sensitive_key(
                    key_text
                ):
                    sanitized[key_text] = _REDACTED
                    continue

                sanitized[key_text] = (
                    cls.sanitize(item)
                )

            return sanitized

        if isinstance(value, (list, tuple, set)):
            return [
                cls.sanitize(item)
                for item in value
            ]

        if isinstance(value, uuid.UUID):
            return str(value)

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, date):
            return value.isoformat()

        if isinstance(value, Decimal):
            return str(value)

        if isinstance(value, bytes):
            return _REDACTED

        if isinstance(value, str):
            return cls._sanitize_string(
                value
            )

        if isinstance(
            value,
            (bool, int, float),
        ):
            return value

        return str(value)


class AuditService:
    DEFAULT_CHAIN_SCOPE = "GLOBAL"

    @classmethod
    def _validate_choice(
        cls,
        *,
        value: str,
        choices,
        field_name: str,
    ) -> str:
        normalized = value.strip().upper()

        valid_values = {
            choice[0]
            for choice in choices
        }

        if normalized not in valid_values:
            raise ValueError(
                f"Invalid {field_name}: "
                f"{normalized}"
            )

        return normalized

    @classmethod
    def _normalize_required_text(
        cls,
        value: str,
        *,
        field_name: str,
        max_length: int,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                f"{field_name} is required."
            )

        if len(value) > max_length:
            raise ValueError(
                f"{field_name} exceeds "
                f"{max_length} characters."
            )

        return value

    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        *,
        max_length: int,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        if len(value) > max_length:
            value = value[:max_length]

        return LogSanitizer._sanitize_string(
            value
        )

    @classmethod
    def _normalize_chain_scope(
        cls,
        chain_scope: str | None,
    ) -> str:
        if chain_scope is None:
            return cls.DEFAULT_CHAIN_SCOPE

        chain_scope = (
            chain_scope
            .strip()
            .upper()
        )

        if not chain_scope:
            return cls.DEFAULT_CHAIN_SCOPE

        if len(chain_scope) > 50:
            raise ValueError(
                "chain_scope exceeds "
                "50 characters."
            )

        return chain_scope

    @classmethod
    def _lock_id_for_scope(
        cls,
        chain_scope: str,
    ) -> int:
        digest = hashlib.sha256(
            (
                "gpc-lopdp:audit-chain:"
                f"{chain_scope}"
            ).encode("utf-8")
        ).digest()

        return int.from_bytes(
            digest[:8],
            byteorder="big",
            signed=True,
        )

    @classmethod
    def _acquire_chain_lock_and_db_time(
        cls,
        chain_scope: str,
    ):
        lock_id = cls._lock_id_for_scope(
            chain_scope
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "pg_advisory_xact_lock(%s)",
                [lock_id],
            )

            cursor.execute(
                "SELECT transaction_timestamp()"
            )

            row = cursor.fetchone()

        return row[0]

    @classmethod
    def _resolve_actor(
        cls,
        *,
        actor_type: str,
        actor,
    ):
        user_model = get_user_model()

        if (
            actor_type
            == AuditLog.ActorType.SYSTEM
        ):
            if actor is not None:
                raise AuditActorError(
                    "SYSTEM audit entries "
                    "must not have actor_user."
                )

            return None

        actor_id = getattr(
            actor,
            "pk",
            None,
        )

        if actor_id is None:
            raise AuditActorError(
                "USER audit entries require "
                "an active persisted user."
            )

        persisted_actor = (
            user_model.objects
            .filter(
                pk=actor_id,
                is_active=True,
            )
            .first()
        )

        if persisted_actor is None:
            raise AuditActorError(
                "USER audit entries require "
                "an active persisted user."
            )

        return persisted_actor

    @classmethod
    def _canonical_payload(
        cls,
        *,
        actor_type: str,
        actor_user_id,
        source: str,
        correlation_id: uuid.UUID,
        action: str,
        entity_type: str,
        entity_pk: str | None,
        description: str | None,
        reason_encrypted: bytes | None,
        encryption_key_version: int,
        previous_values,
        new_values,
        metadata,
        ip_address: str | None,
        user_agent: str | None,
        chain_scope: str,
        chain_position: int,
        previous_hash: str | None,
        created_at,
    ) -> dict[str, Any]:
        return {
            "actor_type": actor_type,
            "actor_user_id": (
                str(actor_user_id)
                if actor_user_id is not None
                else None
            ),
            "source": source,
            "correlation_id": str(
                correlation_id
            ),
            "action": action,
            "entity_type": entity_type,
            "entity_pk": entity_pk,
            "description": description,
            "reason_encrypted": (
                base64.b64encode(
                    reason_encrypted
                ).decode("ascii")
                if reason_encrypted
                else None
            ),
            "encryption_key_version": (
                encryption_key_version
            ),
            "previous_values": (
                previous_values
            ),
            "new_values": new_values,
            "metadata": metadata,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "chain_scope": chain_scope,
            "chain_position": chain_position,
            "previous_hash": previous_hash,
            "created_at": (
                created_at.isoformat()
            ),
        }

    @classmethod
    def _hash_payload(
        cls,
        payload: dict[str, Any],
    ) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return hashlib.sha256(
            canonical
        ).hexdigest()

    @classmethod
    def write(
        cls,
        *,
        action: str,
        entity_type: str,
        actor_type: str = AuditLog.ActorType.USER,
        actor=None,
        source: str = AuditLog.Source.WEB,
        correlation_id: uuid.UUID | None = None,
        entity_pk=None,
        description: str | None = None,
        reason: str | None = None,
        previous_values=None,
        new_values=None,
        metadata=None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        chain_scope: str = DEFAULT_CHAIN_SCOPE,
    ) -> AuditLog:
        actor_type = cls._validate_choice(
            value=actor_type,
            choices=AuditLog.ActorType.choices,
            field_name="actor_type",
        )

        source = cls._validate_choice(
            value=source,
            choices=AuditLog.Source.choices,
            field_name="source",
        )

        action = cls._normalize_required_text(
            action,
            field_name="action",
            max_length=100,
        )

        entity_type = (
            cls._normalize_required_text(
                entity_type,
                field_name="entity_type",
                max_length=50,
            )
        )

        chain_scope = (
            cls._normalize_chain_scope(
                chain_scope
            )
        )

        actor_user = cls._resolve_actor(
            actor_type=actor_type,
            actor=actor,
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

        if entity_pk is not None:
            entity_pk = str(entity_pk)

        description = (
            cls._normalize_optional_text(
                description,
                max_length=500,
            )
        )

        user_agent = (
            cls._normalize_optional_text(
                user_agent,
                max_length=500,
            )
        )

        previous_values = (
            LogSanitizer.sanitize(
                previous_values
            )
            if previous_values is not None
            else None
        )

        new_values = (
            LogSanitizer.sanitize(
                new_values
            )
            if new_values is not None
            else None
        )

        metadata = LogSanitizer.sanitize(
            metadata or {}
        )

        encryption_key_version = (
            settings.PII_ENCRYPTION_ACTIVE_VERSION
        )

        with transaction.atomic():
            created_at = (
                cls
                ._acquire_chain_lock_and_db_time(
                    chain_scope
                )
            )

            last_entry = (
                AuditLog.objects
                .filter(
                    chain_scope=chain_scope
                )
                .order_by(
                    "-chain_position"
                )
                .first()
            )

            if last_entry is None:
                chain_position = 1
                previous_hash = None
            else:
                chain_position = (
                    last_entry
                    .chain_position
                    + 1
                )

                previous_hash = (
                    last_entry.entry_hash
                )

            reason_encrypted = None

            if (
                reason is not None
                and reason.strip()
            ):
                encrypted_reason = (
                    CryptoService.encrypt_text(
                        reason.strip(),
                        aad=(
                            f"audit_logs:"
                            f"{chain_scope}:"
                            f"{chain_position}:"
                            f"{correlation_id}:"
                            f"reason"
                        ),
                        key_version=(
                            encryption_key_version
                        ),
                    )
                )

                reason_encrypted = (
                    encrypted_reason.data
                )

            payload = cls._canonical_payload(
                actor_type=actor_type,
                actor_user_id=(
                    actor_user.pk
                    if actor_user
                    else None
                ),
                source=source,
                correlation_id=(
                    correlation_id
                ),
                action=action,
                entity_type=entity_type,
                entity_pk=entity_pk,
                description=description,
                reason_encrypted=(
                    reason_encrypted
                ),
                encryption_key_version=(
                    encryption_key_version
                ),
                previous_values=(
                    previous_values
                ),
                new_values=new_values,
                metadata=metadata,
                ip_address=ip_address,
                user_agent=user_agent,
                chain_scope=chain_scope,
                chain_position=(
                    chain_position
                ),
                previous_hash=(
                    previous_hash
                ),
                created_at=created_at,
            )

            entry_hash = cls._hash_payload(
                payload
            )

            return AuditLog.objects.create(
                actor_type=actor_type,
                actor_user=actor_user,
                source=source,
                correlation_id=(
                    correlation_id
                ),
                action=action,
                entity_type=entity_type,
                entity_pk=entity_pk,
                description=description,
                reason_encrypted=(
                    reason_encrypted
                ),
                encryption_key_version=(
                    encryption_key_version
                ),
                previous_values=(
                    previous_values
                ),
                new_values=new_values,
                metadata=metadata,
                ip_address=ip_address,
                user_agent=user_agent,
                chain_scope=chain_scope,
                chain_position=(
                    chain_position
                ),
                previous_hash=(
                    previous_hash
                ),
                entry_hash=entry_hash,
                created_at=created_at,
            )

    @classmethod
    def verify_chain(
        cls,
        *,
        chain_scope: str = DEFAULT_CHAIN_SCOPE,
    ) -> AuditChainVerificationResult:
        chain_scope = (
            cls._normalize_chain_scope(
                chain_scope
            )
        )

        entries = list(
            AuditLog.objects
            .filter(
                chain_scope=chain_scope
            )
            .order_by(
                "chain_position"
            )
        )

        expected_position = 1
        expected_previous_hash = None

        for entry in entries:
            if (
                entry.chain_position
                != expected_position
            ):
                raise AuditChainIntegrityError(
                    chain_scope=chain_scope,
                    chain_position=(
                        entry.chain_position
                    ),
                    message=(
                        "Unexpected chain position."
                    ),
                )

            if (
                entry.previous_hash
                != expected_previous_hash
            ):
                raise AuditChainIntegrityError(
                    chain_scope=chain_scope,
                    chain_position=(
                        entry.chain_position
                    ),
                    message=(
                        "previous_hash mismatch."
                    ),
                )

            payload = cls._canonical_payload(
                actor_type=entry.actor_type,
                actor_user_id=(
                    entry.actor_user_id
                ),
                source=entry.source,
                correlation_id=(
                    entry.correlation_id
                ),
                action=entry.action,
                entity_type=(
                    entry.entity_type
                ),
                entity_pk=entry.entity_pk,
                description=(
                    entry.description
                ),
                reason_encrypted=(
                    bytes(
                        entry.reason_encrypted
                    )
                    if entry.reason_encrypted
                    else None
                ),
                encryption_key_version=(
                    entry.encryption_key_version
                ),
                previous_values=(
                    entry.previous_values
                ),
                new_values=(
                    entry.new_values
                ),
                metadata=entry.metadata,
                ip_address=(
                    entry.ip_address
                ),
                user_agent=(
                    entry.user_agent
                ),
                chain_scope=(
                    entry.chain_scope
                ),
                chain_position=(
                    entry.chain_position
                ),
                previous_hash=(
                    entry.previous_hash
                ),
                created_at=entry.created_at,
            )

            calculated_hash = (
                cls._hash_payload(
                    payload
                )
            )

            if (
                calculated_hash
                != entry.entry_hash
            ):
                raise AuditChainIntegrityError(
                    chain_scope=chain_scope,
                    chain_position=(
                        entry.chain_position
                    ),
                    message=(
                        "entry_hash mismatch."
                    ),
                )

            expected_previous_hash = (
                entry.entry_hash
            )

            expected_position += 1

        return AuditChainVerificationResult(
            chain_scope=chain_scope,
            checked_entries=len(entries),
        )
