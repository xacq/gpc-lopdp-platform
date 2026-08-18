from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import quote, urlencode

import qrcode
import qrcode.image.svg

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import MFADevice
from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.core.services.crypto import CryptoService


class MFAError(Exception):
    """Base exception for multi-factor authentication."""


class MFARejected(MFAError):
    """A deliberately generic MFA rejection."""


class MFAEnrollmentRequired(MFAError):
    """The user has no confirmed TOTP device."""


@dataclass(frozen=True)
class TOTPEnrollment:
    device: MFADevice
    secret: str
    provisioning_uri: str
    qr_data_uri: str


@dataclass(frozen=True)
class MFAConfirmation:
    device: MFADevice
    recovery_codes: tuple[str, ...]


class MFAService:
    """TOTP enrollment, verification and recovery-code lifecycle."""

    TOTP_PERIOD_SECONDS = 30
    TOTP_DIGITS = 6
    TOTP_SECRET_BYTES = 20

    @classmethod
    def _issuer(cls) -> str:
        issuer = str(
            getattr(settings, "MFA_TOTP_ISSUER", "VINESA")
        ).strip()
        if not issuer:
            raise ValueError("MFA_TOTP_ISSUER cannot be empty.")
        return issuer

    @classmethod
    def _recovery_code_count(cls) -> int:
        count = int(getattr(settings, "MFA_RECOVERY_CODE_COUNT", 10))
        if count <= 0:
            raise ValueError("MFA_RECOVERY_CODE_COUNT must be positive.")
        return count

    @staticmethod
    def _aad(device_id) -> str:
        return f"mfa_devices:{device_id}:secret"

    @classmethod
    def _encrypt(cls, plaintext: bytes, *, device_id):
        return CryptoService.encrypt_bytes(
            plaintext,
            aad=cls._aad(device_id),
        )

    @classmethod
    def _decrypt(cls, device: MFADevice) -> bytes:
        return CryptoService.decrypt_bytes(
            bytes(device.secret_encrypted),
            aad=cls._aad(device.pk),
            key_version=device.encryption_key_version,
        )

    @staticmethod
    def _normalize_totp(code: str) -> str:
        if not isinstance(code, str):
            raise MFARejected("MFA verification failed.")
        normalized = code.strip().replace(" ", "")
        if (
            len(normalized) != 6
            or not normalized.isascii()
            or not normalized.isdigit()
        ):
            raise MFARejected("MFA verification failed.")
        return normalized

    @staticmethod
    def _normalize_recovery_code(code: str) -> str:
        if not isinstance(code, str):
            raise MFARejected("MFA verification failed.")
        normalized = "".join(
            character
            for character in code.upper()
            if character.isalnum()
        )
        if len(normalized) != 16:
            raise MFARejected("MFA verification failed.")
        return normalized

    @classmethod
    def _totp_at_counter(cls, secret: str, counter: int) -> str:
        padding = "=" * ((8 - len(secret) % 8) % 8)
        key = base64.b32decode(secret + padding, casefold=True)
        digest = hmac.new(
            key,
            struct.pack(">Q", counter),
            hashlib.sha1,
        ).digest()
        offset = digest[-1] & 0x0F
        value = (
            struct.unpack(">I", digest[offset : offset + 4])[0]
            & 0x7FFFFFFF
        )
        return str(value % (10**cls.TOTP_DIGITS)).zfill(
            cls.TOTP_DIGITS
        )

    @classmethod
    def generate_totp_code(cls, secret: str, *, at=None) -> str:
        """Return the RFC 6238 code; exposed for deterministic tests."""
        at = at or timezone.now()
        counter = int(at.timestamp()) // cls.TOTP_PERIOD_SECONDS
        return cls._totp_at_counter(secret, counter)

    @classmethod
    def _matching_counter(
        cls,
        secret: str,
        code: str,
        *,
        now,
    ) -> int | None:
        normalized = cls._normalize_totp(code)
        current = int(now.timestamp()) // cls.TOTP_PERIOD_SECONDS
        for counter in (current - 1, current, current + 1):
            expected = cls._totp_at_counter(secret, counter)
            if hmac.compare_digest(expected, normalized):
                return counter
        return None

    @classmethod
    def has_confirmed_totp(cls, *, user) -> bool:
        return MFADevice.objects.filter(
            user=user,
            device_type=MFADevice.DeviceType.TOTP,
            is_confirmed=True,
            is_active=True,
            revoked_at__isnull=True,
        ).exists()

    @classmethod
    @transaction.atomic
    def begin_totp_enrollment(cls, *, user) -> TOTPEnrollment:
        type(user).objects.select_for_update().get(pk=user.pk)

        if cls.has_confirmed_totp(user=user):
            raise MFARejected("MFA enrollment is unavailable.")

        device = (
            MFADevice.objects.select_for_update()
            .filter(
                user=user,
                device_type=MFADevice.DeviceType.TOTP,
                is_confirmed=False,
                is_active=True,
                revoked_at__isnull=True,
            )
            .order_by("created_at")
            .first()
        )

        if device is None:
            device = MFADevice(
                user=user,
                device_name="Aplicación de autenticación",
                device_type=MFADevice.DeviceType.TOTP,
            )
            secret = base64.b32encode(
                secrets.token_bytes(cls.TOTP_SECRET_BYTES)
            ).decode("ascii").rstrip("=")
            encrypted = cls._encrypt(
                secret.encode("ascii"),
                device_id=device.pk,
            )
            device.secret_encrypted = encrypted.data
            device.encryption_key_version = encrypted.key_version
            device.save()
        else:
            secret = cls._decrypt(device).decode("ascii")

        issuer = cls._issuer()
        label = f"{issuer}:{user.email}"
        provisioning_uri = (
            f"otpauth://totp/{quote(label, safe='')}?"
            + urlencode(
                {
                    "secret": secret,
                    "issuer": issuer,
                    "algorithm": "SHA1",
                    "digits": cls.TOTP_DIGITS,
                    "period": cls.TOTP_PERIOD_SECONDS,
                }
            )
        )
        qr_buffer = BytesIO()
        qr_image = qrcode.make(
            provisioning_uri,
            image_factory=qrcode.image.svg.SvgPathImage,
            box_size=8,
            border=4,
        )
        qr_image.save(qr_buffer)
        qr_data_uri = (
            "data:image/svg+xml;base64,"
            + base64.b64encode(qr_buffer.getvalue()).decode("ascii")
        )
        return TOTPEnrollment(
            device=device,
            secret=secret,
            provisioning_uri=provisioning_uri,
            qr_data_uri=qr_data_uri,
        )

    @classmethod
    def _create_recovery_device(
        cls,
        *,
        user,
        now,
    ) -> tuple[MFADevice, tuple[str, ...]]:
        existing = (
            MFADevice.objects.select_for_update()
            .filter(
                user=user,
                device_type=MFADevice.DeviceType.RECOVERY_CODES,
                is_active=True,
                revoked_at__isnull=True,
            )
            .first()
        )
        if existing is not None:
            raise MFARejected("MFA enrollment is unavailable.")

        raw_codes = tuple(
            secrets.token_hex(8).upper()
            for _ in range(cls._recovery_code_count())
        )
        codes = tuple(
            "-".join(
                raw[index : index + 4]
                for index in range(0, 16, 4)
            )
            for raw in raw_codes
        )
        digests = [
            CryptoService.lookup_hash(
                cls._normalize_recovery_code(code)
            )
            for code in codes
        ]
        lookup_key_version = digests[0].key_version
        payload = {
            "lookup_key_version": lookup_key_version,
            "hashes": [digest.value for digest in digests],
        }
        device = MFADevice(
            user=user,
            device_name="Códigos de recuperación",
            device_type=MFADevice.DeviceType.RECOVERY_CODES,
            is_confirmed=True,
            confirmed_at=now,
        )
        encrypted = cls._encrypt(
            json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8"),
            device_id=device.pk,
        )
        device.secret_encrypted = encrypted.data
        device.encryption_key_version = encrypted.key_version
        device.save()
        return device, codes

    @classmethod
    @transaction.atomic
    def confirm_totp(
        cls,
        *,
        user,
        device_id,
        code: str,
        now=None,
    ) -> MFAConfirmation:
        now = now or timezone.now()
        device = (
            MFADevice.objects.select_for_update()
            .filter(
                pk=device_id,
                user=user,
                device_type=MFADevice.DeviceType.TOTP,
                is_confirmed=False,
                is_active=True,
                revoked_at__isnull=True,
            )
            .first()
        )
        if device is None:
            raise MFARejected("MFA verification failed.")

        secret = cls._decrypt(device).decode("ascii")
        try:
            counter = cls._matching_counter(
                secret,
                code,
                now=now,
            )
        except MFARejected:
            cls._audit_rejected(
                user=user,
                method="TOTP_ENROLLMENT",
            )
            raise
        if counter is None:
            cls._audit_rejected(user=user, method="TOTP_ENROLLMENT")
            raise MFARejected("MFA verification failed.")

        device.is_confirmed = True
        device.confirmed_at = now
        device.last_used_at = now
        device.save(
            update_fields=["is_confirmed", "confirmed_at", "last_used_at"]
        )
        _, recovery_codes = cls._create_recovery_device(
            user=user,
            now=now,
        )
        cls._audit_accepted(user=user, method="TOTP_ENROLLMENT")
        return MFAConfirmation(
            device=device,
            recovery_codes=recovery_codes,
        )

    @classmethod
    @transaction.atomic
    def verify_totp(cls, *, user, code: str, now=None) -> MFADevice:
        now = now or timezone.now()
        device = (
            MFADevice.objects.select_for_update()
            .filter(
                user=user,
                device_type=MFADevice.DeviceType.TOTP,
                is_confirmed=True,
                is_active=True,
                revoked_at__isnull=True,
            )
            .order_by("created_at")
            .first()
        )
        if device is None:
            raise MFAEnrollmentRequired("TOTP enrollment is required.")

        secret = cls._decrypt(device).decode("ascii")
        try:
            counter = cls._matching_counter(
                secret,
                code,
                now=now,
            )
        except MFARejected:
            cls._audit_rejected(user=user, method="TOTP")
            raise
        last_counter = (
            int(device.last_used_at.timestamp())
            // cls.TOTP_PERIOD_SECONDS
            if device.last_used_at is not None
            else None
        )
        if counter is None or (
            last_counter is not None
            and counter <= last_counter
        ):
            cls._audit_rejected(user=user, method="TOTP")
            raise MFARejected("MFA verification failed.")

        device.last_used_at = now
        device.save(update_fields=["last_used_at"])
        cls._audit_accepted(user=user, method="TOTP")
        return device

    @classmethod
    @transaction.atomic
    def consume_recovery_code(
        cls,
        *,
        user,
        code: str,
        now=None,
    ) -> MFADevice:
        now = now or timezone.now()
        try:
            normalized = cls._normalize_recovery_code(code)
        except MFARejected:
            cls._audit_rejected(
                user=user,
                method="RECOVERY_CODE",
            )
            raise
        device = (
            MFADevice.objects.select_for_update()
            .filter(
                user=user,
                device_type=MFADevice.DeviceType.RECOVERY_CODES,
                is_confirmed=True,
                is_active=True,
                revoked_at__isnull=True,
            )
            .first()
        )
        if device is None:
            cls._audit_rejected(user=user, method="RECOVERY_CODE")
            raise MFARejected("MFA verification failed.")

        payload = json.loads(
            cls._decrypt(device).decode("utf-8")
        )
        hashes = payload["hashes"]
        candidate_hash = CryptoService.lookup_hash(
            normalized,
            key_version=int(payload["lookup_key_version"]),
        ).value
        matched_index = next(
            (
                index
                for index, value in enumerate(hashes)
                if hmac.compare_digest(candidate_hash, value)
            ),
            None,
        )
        if matched_index is None:
            cls._audit_rejected(user=user, method="RECOVERY_CODE")
            raise MFARejected("MFA verification failed.")

        hashes.pop(matched_index)
        payload["hashes"] = hashes
        encrypted = cls._encrypt(
            json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8"),
            device_id=device.pk,
        )
        device.secret_encrypted = encrypted.data
        device.encryption_key_version = encrypted.key_version
        device.last_used_at = now
        device.save(
            update_fields=[
                "secret_encrypted",
                "encryption_key_version",
                "last_used_at",
            ]
        )
        cls._audit_accepted(user=user, method="RECOVERY_CODE")
        return device

    @classmethod
    @transaction.atomic
    def revoke(cls, *, device: MFADevice, actor) -> MFADevice:
        persisted = MFADevice.objects.select_for_update().get(pk=device.pk)
        if not persisted.is_active or persisted.revoked_at is not None:
            raise MFARejected("MFA device is unavailable.")
        now = timezone.now()
        persisted.is_active = False
        persisted.revoked_at = now
        persisted.save(update_fields=["is_active", "revoked_at"])
        AuditService.write(
            action="MFA_DEVICE_REVOKED",
            entity_type="MFA_DEVICE",
            entity_pk=persisted.pk,
            actor_type=AuditLog.ActorType.USER,
            actor=actor,
            metadata={"device_type": persisted.device_type},
        )
        return persisted

    @classmethod
    def _audit_accepted(cls, *, user, method: str):
        return AuditService.write(
            action="AUTH_MFA_ACCEPTED",
            entity_type="USER",
            entity_pk=user.pk,
            actor_type=AuditLog.ActorType.USER,
            actor=user,
            metadata={"mfa_method": method},
        )

    @classmethod
    def _audit_rejected(cls, *, user, method: str):
        return AuditService.write(
            action="AUTH_MFA_REJECTED",
            entity_type="USER",
            entity_pk=user.pk,
            actor_type=AuditLog.ActorType.SYSTEM,
            actor=None,
            metadata={"mfa_method": method},
        )
