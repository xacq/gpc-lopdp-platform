from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import (
    RequestAccessToken,
    RequestResolution,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseActorError,
    CasePermissionError,
    CaseWorkflowService,
)
from apps.cases.services.tokens import (
    RequestAccessTokenService,
    TokenInvalidOrExpiredError,
)
from apps.communications.models import PortabilityExport
from apps.core.services.storage import (
    LocalPrivateStorageService,
    PrivateStorageError,
)
from apps.subjects.services.subjects import SubjectService


class PortabilityServiceError(Exception):
    pass


class PortabilityNotAllowedError(PortabilityServiceError):
    pass


class PortabilityAccessError(PortabilityServiceError):
    pass


class PortabilityIntegrityError(PortabilityServiceError):
    pass


@dataclass(frozen=True)
class GeneratedPortabilityExport:
    export: PortabilityExport
    download_token: str


@dataclass(frozen=True)
class PortabilityDownload:
    content: bytes
    content_type: str
    filename: str


class PortabilityService:
    ALLOWED_RESOLUTIONS = {
        RequestResolution.ResolutionType.APPROVED,
        RequestResolution.ResolutionType.PARTIALLY_APPROVED,
    }

    @classmethod
    def _normalize_format(cls, export_format: str) -> str:
        normalized = str(export_format).strip().upper()
        valid = {choice[0] for choice in PortabilityExport.ExportFormat.choices}
        if normalized not in valid:
            raise ValueError("Unsupported portability export format.")
        return normalized

    @classmethod
    def _require_generation_permission(cls, actor) -> None:
        try:
            actor = CaseWorkflowService._validate_actor(actor)
            CaseWorkflowService._require_manager_permission(actor)
        except (CaseActorError, CasePermissionError, ValueError) as exc:
            raise PortabilityAccessError(
                "Actor is not allowed to generate portability exports."
            ) from exc

    @classmethod
    def _validate_request(cls, request: RightsRequest) -> RequestResolution:
        allowed_codes = {
            value.strip().upper()
            for value in getattr(settings, "PORTABILITY_RIGHT_CODES", ["PORTABILITY"])
            if value and value.strip()
        }
        if request.right.code.strip().upper() not in allowed_codes:
            raise PortabilityNotAllowedError(
                "Request does not exercise the portability right."
            )

        resolution = RequestResolution.objects.filter(request=request).first()
        if resolution is None or resolution.resolution_type not in cls.ALLOWED_RESOLUTIONS:
            raise PortabilityNotAllowedError(
                "An approved resolution is required for portability."
            )
        return resolution

    @classmethod
    def _payload(cls, request: RightsRequest) -> dict:
        subject = SubjectService.decrypt(request.data_subject)
        snapshot = CaseWorkflowService.decrypt_subject_snapshot(request)
        return {
            "schema_version": "1.0",
            "request": {
                "reference_number": request.reference_number,
                "right": request.right.code,
                "status": request.status,
                "identity_status": request.identity_status,
                "received_at": request.received_at.isoformat(),
                "details": CaseWorkflowService.decrypt_request_details(request),
            },
            "data_subject": {
                "subject_type": subject.subject_type,
                "document_type": subject.document_type,
                "document_number": subject.document_number,
                "full_name": subject.full_name,
                "email": subject.email,
                "phone": subject.phone,
            },
            "submitted_snapshot": {
                "full_name": snapshot.full_name,
                "email": snapshot.email,
                "phone": snapshot.phone,
            },
        }

    @classmethod
    def _serialize(cls, payload: dict, export_format: str) -> bytes:
        if export_format == PortabilityExport.ExportFormat.JSON:
            return json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")

        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["section", "field", "value"])
        for section in ("request", "data_subject", "submitted_snapshot"):
            for field, value in payload[section].items():
                writer.writerow([section, field, "" if value is None else value])
        writer.writerow(["metadata", "schema_version", payload["schema_version"]])
        return output.getvalue().encode("utf-8")

    @classmethod
    def generate(
        cls,
        *,
        request: RightsRequest,
        export_format: str,
        actor,
        correlation_id=None,
    ) -> GeneratedPortabilityExport:
        cls._require_generation_permission(actor)
        export_format = cls._normalize_format(export_format)
        correlation_id = uuid.UUID(str(correlation_id)) if correlation_id else uuid.uuid4()
        ttl = timedelta(
            seconds=int(getattr(settings, "PORTABILITY_DOWNLOAD_TTL_SECONDS", 86400))
        )
        if ttl <= timedelta(0):
            raise ValueError("PORTABILITY_DOWNLOAD_TTL_SECONDS must be positive.")

        export_id = uuid.uuid4()
        extension = export_format.lower()
        storage_key = f"portability/{request.id}/{export_id}.{extension}.bin"
        stored = False

        try:
            with transaction.atomic():
                locked = (
                    RightsRequest.objects.select_for_update()
                    .select_related("right", "data_subject")
                    .get(pk=request.pk)
                )
                cls._validate_request(locked)
                content = cls._serialize(cls._payload(locked), export_format)
                digest = hashlib.sha256(content).hexdigest()
                key_version = int(settings.PII_ENCRYPTION_ACTIVE_VERSION)
                db_now = CaseWorkflowService._database_now()

                LocalPrivateStorageService.write_encrypted(
                    storage_key=storage_key,
                    plaintext=content,
                    key_version=key_version,
                )
                stored = True
                export = PortabilityExport.objects.create(
                    id=export_id,
                    request=locked,
                    export_format=export_format,
                    storage_backend=PortabilityExport.StorageBackend.LOCAL,
                    storage_key=storage_key,
                    file_sha256=digest,
                    is_encrypted=True,
                    encryption_key_version=key_version,
                    generated_by=actor,
                    generated_at=db_now,
                    expires_at=db_now + ttl,
                )
                issued = RequestAccessTokenService.issue(
                    request=locked,
                    purpose=RequestAccessToken.Purpose.PORTABILITY_DOWNLOAD,
                    ttl=ttl,
                    resource_type=RequestAccessToken.ResourceType.PORTABILITY_EXPORT,
                    resource_id=export.id,
                    actor=actor,
                    correlation_id=correlation_id,
                    source=AuditLog.Source.WEB,
                )
                AuditService.write(
                    actor_type=AuditLog.ActorType.USER,
                    actor=actor,
                    source=AuditLog.Source.WEB,
                    correlation_id=correlation_id,
                    action="PORTABILITY_EXPORT_GENERATED",
                    entity_type="PORTABILITY_EXPORT",
                    entity_pk=export.id,
                    description="Encrypted portability export generated.",
                    metadata={
                        "request_id": str(locked.id),
                        "export_format": export_format,
                        "expires_at": export.expires_at.isoformat(),
                    },
                )
                return GeneratedPortabilityExport(
                    export=export,
                    download_token=issued.token,
                )
        except Exception:
            if stored:
                LocalPrivateStorageService.delete(storage_key=storage_key)
            raise

    @classmethod
    def download(
        cls,
        *,
        export: PortabilityExport,
        token: str,
        correlation_id=None,
    ) -> PortabilityDownload:
        correlation_id = uuid.UUID(str(correlation_id)) if correlation_id else uuid.uuid4()
        try:
            with transaction.atomic():
                persisted = (
                    PortabilityExport.objects.select_for_update()
                    .select_related("request")
                    .get(pk=export.pk)
                )
                now = timezone.now()
                if (
                    persisted.revoked_at is not None
                    or persisted.downloaded_at is not None
                    or (persisted.expires_at is not None and persisted.expires_at <= now)
                ):
                    raise PortabilityAccessError("Portability export is unavailable.")

                RequestAccessTokenService.consume(
                    request=persisted.request,
                    token=token,
                    purpose=RequestAccessToken.Purpose.PORTABILITY_DOWNLOAD,
                    resource_type=RequestAccessToken.ResourceType.PORTABILITY_EXPORT,
                    resource_id=persisted.id,
                    actor=None,
                    correlation_id=correlation_id,
                    source=AuditLog.Source.WEB,
                )
                try:
                    content = LocalPrivateStorageService.read_encrypted(
                        storage_key=persisted.storage_key,
                        key_version=persisted.encryption_key_version,
                    )
                except PrivateStorageError as exc:
                    raise PortabilityIntegrityError(
                        "Portability export could not be read securely."
                    ) from exc
                if hashlib.sha256(content).hexdigest() != persisted.file_sha256:
                    raise PortabilityIntegrityError(
                        "Portability export integrity validation failed."
                    )

                persisted.downloaded_at = now
                persisted.save(update_fields=["downloaded_at"])
                AuditService.write(
                    actor_type=AuditLog.ActorType.SYSTEM,
                    actor=None,
                    source=AuditLog.Source.WEB,
                    correlation_id=correlation_id,
                    action="PORTABILITY_EXPORT_DOWNLOADED",
                    entity_type="PORTABILITY_EXPORT",
                    entity_pk=persisted.id,
                    description="Portability export downloaded.",
                    metadata={
                        "request_id": str(persisted.request_id),
                        "export_format": persisted.export_format,
                    },
                )
                extension = persisted.export_format.lower()
                content_type = (
                    "application/json"
                    if persisted.export_format == PortabilityExport.ExportFormat.JSON
                    else "text/csv; charset=utf-8"
                )
                return PortabilityDownload(
                    content=content,
                    content_type=content_type,
                    filename=f"portabilidad-{persisted.request.reference_number}.{extension}",
                )
        except TokenInvalidOrExpiredError as exc:
            raise PortabilityAccessError("Portability export is unavailable.") from exc

    @classmethod
    def revoke(
        cls,
        *,
        export: PortabilityExport,
        actor,
        correlation_id=None,
    ) -> PortabilityExport:
        cls._require_generation_permission(actor)
        correlation_id = (
            uuid.UUID(str(correlation_id)) if correlation_id else uuid.uuid4()
        )
        with transaction.atomic():
            persisted = PortabilityExport.objects.select_for_update().get(
                pk=export.pk
            )
            if persisted.revoked_at is not None:
                return persisted
            if persisted.downloaded_at is not None:
                raise PortabilityAccessError(
                    "A downloaded portability export cannot be revoked."
                )
            persisted.revoked_at = CaseWorkflowService._database_now()
            persisted.save(update_fields=["revoked_at"])
            RequestAccessToken.objects.filter(
                resource_type=RequestAccessToken.ResourceType.PORTABILITY_EXPORT,
                resource_id=persisted.id,
                revoked_at__isnull=True,
            ).update(revoked_at=persisted.revoked_at)
            AuditService.write(
                actor_type=AuditLog.ActorType.USER,
                actor=actor,
                source=AuditLog.Source.WEB,
                correlation_id=correlation_id,
                action="PORTABILITY_EXPORT_REVOKED",
                entity_type="PORTABILITY_EXPORT",
                entity_pk=persisted.id,
                description="Portability export revoked.",
                metadata={
                    "request_id": str(persisted.request_id),
                    "export_format": persisted.export_format,
                },
            )
            return persisted
