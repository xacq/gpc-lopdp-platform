from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.organization.models import SystemSetting
from apps.organization.policies import can_manage_system_settings


_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}$"
)
_PREFIX_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,9}$")


class SystemSettingsError(Exception):
    """Base exception for institutional configuration."""


class SystemSettingsPermissionError(SystemSettingsError):
    pass


class SystemSettingsValidationError(SystemSettingsError):
    pass


class SystemSettingsService:
    EDITABLE_FIELDS = (
        "legal_name",
        "trade_name",
        "ruc",
        "domain",
        "address",
        "phone",
        "contact_email",
        "controller_name",
        "controller_email",
        "controller_phone",
        "dpd_name",
        "dpd_email",
        "dpd_phone",
        "complaint_authority_name",
        "complaint_channel_url",
        "complaint_instructions",
        "request_prefix",
        "timezone",
        "logo_url",
        "favicon_url",
        "primary_color",
        "secondary_color",
        "accent_color",
    )

    @classmethod
    def _require_actor(cls, actor):
        if not can_manage_system_settings(actor):
            raise SystemSettingsPermissionError(
                "System settings administration is not permitted."
            )
        return actor

    @staticmethod
    def _optional(value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @classmethod
    def _normalize(cls, values: dict) -> dict:
        missing = [
            field
            for field in cls.EDITABLE_FIELDS
            if field not in values
        ]
        if missing:
            raise SystemSettingsValidationError(
                "The configuration payload is incomplete."
            )

        normalized = {
            field: cls._optional(values[field])
            for field in cls.EDITABLE_FIELDS
        }
        for required in (
            "legal_name",
            "ruc",
            "domain",
            "contact_email",
            "complaint_authority_name",
            "request_prefix",
            "timezone",
        ):
            if normalized[required] is None:
                raise SystemSettingsValidationError(
                    "Required configuration values are missing."
                )

        normalized["domain"] = normalized["domain"].lower().rstrip(".")
        normalized["contact_email"] = normalized["contact_email"].lower()
        for field in ("controller_email", "dpd_email"):
            if normalized[field] is not None:
                normalized[field] = normalized[field].lower()
        normalized["request_prefix"] = (
            normalized["request_prefix"].upper()
        )
        for field in (
            "primary_color",
            "secondary_color",
            "accent_color",
        ):
            if normalized[field] is not None:
                normalized[field] = normalized[field].upper()
        return normalized

    @classmethod
    def _validate_domain_rules(cls, values: dict) -> None:
        if not values["ruc"].isdigit() or len(values["ruc"]) != 13:
            raise SystemSettingsValidationError(
                "RUC must contain exactly 13 digits."
            )
        if not _DOMAIN_RE.fullmatch(values["domain"]):
            raise SystemSettingsValidationError(
                "The institutional domain is invalid."
            )
        if not _PREFIX_RE.fullmatch(values["request_prefix"]):
            raise SystemSettingsValidationError(
                "The request prefix is invalid."
            )
        try:
            ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise SystemSettingsValidationError(
                "The timezone is invalid."
            ) from exc

        for field in (
            "complaint_channel_url",
            "logo_url",
            "favicon_url",
        ):
            url = values[field]
            if url is None:
                continue
            parsed = urlsplit(url)
            try:
                URLValidator(schemes=["https"])(url)
            except ValidationError as exc:
                raise SystemSettingsValidationError(
                    "External URLs must be valid HTTPS URLs."
                ) from exc
            if parsed.username is not None or parsed.password is not None:
                raise SystemSettingsValidationError(
                    "External URLs must be valid HTTPS URLs."
                )

    @classmethod
    def _acquire_singleton_lock(cls) -> None:
        lock_id = int.from_bytes(
            hashlib.sha256(
                b"gpc-lopdp:system-settings"
            ).digest()[:8],
            byteorder="big",
            signed=True,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                [lock_id],
            )

    @classmethod
    @transaction.atomic
    def save(cls, *, values: dict, actor) -> SystemSetting:
        actor = cls._require_actor(actor)
        normalized = cls._normalize(values)
        cls._validate_domain_rules(normalized)
        cls._acquire_singleton_lock()

        setting = (
            SystemSetting.objects
            .select_for_update()
            .filter(singleton_key=1)
            .first()
        )
        created = setting is None
        if created:
            setting = SystemSetting(singleton_key=1)

        changed_fields = []
        for field in cls.EDITABLE_FIELDS:
            value = normalized[field]
            if getattr(setting, field, None) != value:
                setattr(setting, field, value)
                changed_fields.append(field)

        if not created and not changed_fields:
            return setting

        setting.updated_at = timezone.now()
        try:
            setting.full_clean()
            setting.save()
        except (ValidationError, IntegrityError) as exc:
            raise SystemSettingsValidationError(
                "The institutional configuration is invalid."
            ) from exc

        AuditService.write(
            action=(
                "SYSTEM_SETTINGS_CREATED"
                if created
                else "SYSTEM_SETTINGS_UPDATED"
            ),
            entity_type="SYSTEM_SETTING",
            entity_pk=setting.pk,
            actor_type=AuditLog.ActorType.USER,
            actor=actor,
            metadata={
                "changed_fields": sorted(changed_fields),
                "changed_field_count": len(changed_fields),
            },
        )
        return setting
