from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import RightsRequest
from apps.core.services.crypto import CryptoService
from apps.core.services.storage import LocalPrivateStorageService
from apps.evidence.models import RequestAttachment, TemporaryUpload
from apps.evidence.services.attachments import (
    AttachmentLimitError,
    AttachmentService,
    MalwareScanner,
)


class TemporaryUploadError(Exception):
    pass


class TemporaryUploadAccessError(TemporaryUploadError):
    pass


@dataclass(frozen=True)
class IssuedTemporaryUpload:
    record: TemporaryUpload
    token: str


@dataclass(frozen=True)
class TemporaryUploadCleanupResult:
    selected: int
    deleted: int
    failed: int


class TemporaryUploadService:
    DEFAULT_TTL_SECONDS = 60 * 60

    @classmethod
    def _database_now(cls):
        with connection.cursor() as cursor:
            cursor.execute("SELECT transaction_timestamp()")
            return cursor.fetchone()[0]

    @classmethod
    def _lock_session(cls, session_hash: str) -> None:
        lock_key = int(session_hash[:16], 16)
        if lock_key >= 2**63:
            lock_key -= 2**64
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])

    @classmethod
    def _session_digest(cls, session_key: str, key_version=None):
        if not isinstance(session_key, str) or not session_key.strip():
            raise TemporaryUploadAccessError()
        return CryptoService.lookup_hash(
            f"temporary_upload:session:{session_key.strip()}",
            key_version=key_version,
        )

    @classmethod
    def _token_digest(cls, upload_id, token: str, key_version=None):
        if not isinstance(token, str) or not token.strip():
            raise TemporaryUploadAccessError()
        return CryptoService.lookup_hash(
            f"temporary_upload:token:{upload_id}:{token.strip()}",
            key_version=key_version,
        )

    @classmethod
    def create(
        cls,
        *,
        session_key: str,
        attachment_type: str,
        filename: str,
        declared_mime: str,
        content: bytes,
        scanner: MalwareScanner,
        correlation_id=None,
    ) -> IssuedTemporaryUpload:
        attachment_type = str(attachment_type).strip().upper()
        if attachment_type not in TemporaryUpload.AttachmentType.values:
            raise ValueError("Invalid temporary attachment type.")

        detected_mime = AttachmentService._validate_file(
            filename=filename,
            declared_mime=declared_mime,
            content=content,
        )
        scan_status = AttachmentService._scan(scanner=scanner, content=content)
        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(correlation_id, uuid.UUID):
            correlation_id = uuid.UUID(str(correlation_id))

        ttl_seconds = int(
            getattr(
                settings,
                "PUBLIC_TEMPORARY_UPLOAD_TTL_SECONDS",
                cls.DEFAULT_TTL_SECONDS,
            )
        )
        if ttl_seconds <= 0:
            raise TemporaryUploadError("Temporary upload TTL is invalid.")

        upload_id = uuid.uuid4()
        raw_token = secrets.token_urlsafe(32)
        key_version = int(settings.PII_ENCRYPTION_ACTIVE_VERSION)
        lookup_version = int(settings.LOOKUP_HMAC_ACTIVE_VERSION)
        session_digest = cls._session_digest(session_key, lookup_version)
        token_digest = cls._token_digest(upload_id, raw_token, lookup_version)
        storage_key = f"temporary/{upload_id}.bin"
        filename_encrypted = CryptoService.encrypt_text(
            filename.strip(),
            aad=f"temporary_uploads:{upload_id}:original_filename",
            key_version=key_version,
        )
        file_sha256 = hashlib.sha256(content).hexdigest()
        db_now = cls._database_now()

        LocalPrivateStorageService.write_encrypted(
            storage_key=storage_key,
            plaintext=content,
            key_version=key_version,
        )
        try:
            with transaction.atomic():
                cls._lock_session(session_digest.value)
                active_count = TemporaryUpload.objects.filter(
                    session_key_hash=session_digest.value,
                    status=TemporaryUpload.Status.UPLOADED,
                    expires_at__gt=db_now,
                ).count()
                if active_count >= AttachmentService.MAX_ATTACHMENTS_PER_REQUEST:
                    raise AttachmentLimitError(
                        "Maximum temporary uploads per session reached."
                    )

                record = TemporaryUpload.objects.create(
                    id=upload_id,
                    session_key_hash=session_digest.value,
                    upload_token_hash=token_digest.value,
                    lookup_key_version=lookup_version,
                    attachment_type=attachment_type,
                    original_filename_encrypted=filename_encrypted.data,
                    storage_backend=TemporaryUpload.StorageBackend.LOCAL,
                    storage_key=storage_key,
                    mime_type=detected_mime,
                    size_bytes=len(content),
                    file_sha256=file_sha256,
                    is_encrypted=True,
                    encryption_key_version=key_version,
                    malware_scan_status=scan_status,
                    status=TemporaryUpload.Status.UPLOADED,
                    expires_at=db_now + timedelta(seconds=ttl_seconds),
                    created_at=db_now,
                )
                AuditService.write(
                    actor_type=AuditLog.ActorType.SYSTEM,
                    actor=None,
                    source=AuditLog.Source.WEB,
                    correlation_id=correlation_id,
                    action="PUBLIC_TEMPORARY_UPLOAD_CREATED",
                    entity_type="TEMPORARY_UPLOAD",
                    entity_pk=record.id,
                    description="Encrypted public temporary upload created.",
                    metadata={
                        "attachment_type": attachment_type,
                        "mime_type": detected_mime,
                        "size_bytes": len(content),
                        "malware_scan_status": scan_status,
                    },
                )
        except Exception:
            LocalPrivateStorageService.delete(storage_key=storage_key)
            raise

        return IssuedTemporaryUpload(record=record, token=raw_token)

    @classmethod
    def promote(
        cls,
        *,
        request: RightsRequest,
        upload_id,
        token: str,
        session_key: str,
        correlation_id=None,
    ) -> RequestAttachment:
        try:
            upload_id = uuid.UUID(str(upload_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise TemporaryUploadAccessError() from exc
        if correlation_id is None:
            correlation_id = uuid.uuid4()
        elif not isinstance(correlation_id, uuid.UUID):
            correlation_id = uuid.UUID(str(correlation_id))

        with transaction.atomic():
            locked_request = RightsRequest.objects.select_for_update().get(
                pk=request.pk
            )
            upload = TemporaryUpload.objects.select_for_update().filter(
                pk=upload_id,
                status=TemporaryUpload.Status.UPLOADED,
            ).first()
            if upload is None:
                raise TemporaryUploadAccessError()

            session_digest = cls._session_digest(
                session_key, upload.lookup_key_version
            )
            token_digest = cls._token_digest(
                upload.id, token, upload.lookup_key_version
            )
            if not hmac.compare_digest(
                upload.session_key_hash, session_digest.value
            ) or not hmac.compare_digest(
                upload.upload_token_hash, token_digest.value
            ):
                raise TemporaryUploadAccessError()

            db_now = cls._database_now()
            if upload.expires_at <= db_now:
                upload.status = TemporaryUpload.Status.EXPIRED
                upload.save(update_fields=["status"])
                raise TemporaryUploadAccessError()
            if upload.malware_scan_status != TemporaryUpload.MalwareScanStatus.CLEAN:
                raise TemporaryUploadAccessError()

            content = LocalPrivateStorageService.read_encrypted(
                storage_key=upload.storage_key,
                key_version=upload.encryption_key_version,
            )
            if hashlib.sha256(content).hexdigest() != upload.file_sha256:
                raise TemporaryUploadAccessError()
            if len(content) != upload.size_bytes:
                raise TemporaryUploadAccessError()

            active_count = RequestAttachment.objects.filter(
                request=locked_request,
                deleted_at__isnull=True,
            ).count()
            if active_count >= AttachmentService.MAX_ATTACHMENTS_PER_REQUEST:
                raise AttachmentLimitError(
                    "Maximum attachments per request reached."
                )

            filename = CryptoService.decrypt_text(
                upload.original_filename_encrypted,
                aad=f"temporary_uploads:{upload.id}:original_filename",
                key_version=upload.encryption_key_version,
            )
            attachment_id = uuid.uuid4()
            encrypted_filename = CryptoService.encrypt_text(
                filename,
                aad=(
                    f"request_attachments:{attachment_id}:original_filename"
                ),
                key_version=upload.encryption_key_version,
            )
            representative = (
                locked_request.representative
                if upload.attachment_type
                == TemporaryUpload.AttachmentType.AUTHORITY_DOCUMENT
                else None
            )
            attachment = RequestAttachment.objects.create(
                id=attachment_id,
                request=locked_request,
                representative=representative,
                attachment_type=upload.attachment_type,
                visibility=RequestAttachment.Visibility.INTERNAL,
                original_filename_encrypted=encrypted_filename.data,
                storage_backend=RequestAttachment.StorageBackend.LOCAL,
                storage_key=upload.storage_key,
                mime_type=upload.mime_type,
                size_bytes=upload.size_bytes,
                file_sha256=upload.file_sha256,
                is_encrypted=True,
                encryption_key_version=upload.encryption_key_version,
                malware_scan_status=RequestAttachment.MalwareScanStatus.CLEAN,
                uploaded_by=None,
            )
            upload.status = TemporaryUpload.Status.PROMOTED
            upload.promoted_request = locked_request
            upload.promoted_attachment = attachment
            upload.promoted_at = db_now
            upload.save(
                update_fields=[
                    "status",
                    "promoted_request",
                    "promoted_attachment",
                    "promoted_at",
                ]
            )
            AuditService.write(
                actor_type=AuditLog.ActorType.SYSTEM,
                actor=None,
                source=AuditLog.Source.WEB,
                correlation_id=correlation_id,
                action="PUBLIC_TEMPORARY_UPLOAD_PROMOTED",
                entity_type="REQUEST_ATTACHMENT",
                entity_pk=attachment.id,
                description="Public upload promoted to private request attachment.",
                metadata={
                    "request_id": str(locked_request.id),
                    "temporary_upload_id": str(upload.id),
                    "attachment_type": attachment.attachment_type,
                    "mime_type": attachment.mime_type,
                    "size_bytes": attachment.size_bytes,
                },
            )
            return attachment

    @classmethod
    def discard(cls, *, issued_upload, session_key: str) -> None:
        try:
            upload = issued_upload.record
            session_digest = cls._session_digest(
                session_key, upload.lookup_key_version
            )
            token_digest = cls._token_digest(
                upload.id, issued_upload.token, upload.lookup_key_version
            )
            if not hmac.compare_digest(
                upload.session_key_hash, session_digest.value
            ) or not hmac.compare_digest(
                upload.upload_token_hash, token_digest.value
            ):
                return
            updated = TemporaryUpload.objects.filter(
                pk=upload.pk,
                status=TemporaryUpload.Status.UPLOADED,
            ).update(
                status=TemporaryUpload.Status.DELETED,
                deleted_at=cls._database_now(),
            )
            if updated:
                LocalPrivateStorageService.delete(storage_key=upload.storage_key)
        except Exception:
            return

    @classmethod
    def cleanup_expired(cls, *, batch_size: int = 100):
        if not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000.")
        db_now = cls._database_now()
        upload_ids = list(
            TemporaryUpload.objects.filter(
                status__in=[
                    TemporaryUpload.Status.UPLOADED,
                    TemporaryUpload.Status.EXPIRED,
                ],
                expires_at__lte=db_now,
                deleted_at__isnull=True,
            )
            .order_by("expires_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )
        deleted = 0
        failed = 0

        for upload_id in upload_ids:
            with transaction.atomic():
                upload = TemporaryUpload.objects.select_for_update().filter(
                    pk=upload_id,
                    status__in=[
                        TemporaryUpload.Status.UPLOADED,
                        TemporaryUpload.Status.EXPIRED,
                    ],
                    expires_at__lte=cls._database_now(),
                    deleted_at__isnull=True,
                ).first()
                if upload is None:
                    continue
                upload.status = TemporaryUpload.Status.EXPIRED
                upload.save(update_fields=["status"])

            try:
                LocalPrivateStorageService.delete(
                    storage_key=upload.storage_key
                )
            except Exception:
                failed += 1
                continue

            TemporaryUpload.objects.filter(
                pk=upload.id,
                status=TemporaryUpload.Status.EXPIRED,
                deleted_at__isnull=True,
            ).update(deleted_at=cls._database_now())
            deleted += 1

        return TemporaryUploadCleanupResult(
            selected=len(upload_ids),
            deleted=deleted,
            failed=failed,
        )
