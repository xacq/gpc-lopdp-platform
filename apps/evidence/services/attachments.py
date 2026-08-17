from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import RightsRequest
from apps.core.services.crypto import CryptoService
from apps.core.services.storage import (
    LocalPrivateStorageService,
)
from apps.evidence.models import (
    RequestAttachment,
)
from apps.subjects.models import (
    SubjectRepresentative,
)


class AttachmentServiceError(Exception):
    pass


class FileRejectedError(
    AttachmentServiceError
):
    pass


class AttachmentActorError(
    AttachmentServiceError
):
    pass


class AttachmentLimitError(
    AttachmentServiceError
):
    pass


class AttachmentIntegrityError(
    AttachmentServiceError
):
    pass


class MalwareScannerUnavailableError(
    AttachmentServiceError
):
    pass


class MalwareScanner(Protocol):
    def scan(
        self,
        content: bytes,
    ) -> str:
        ...


@dataclass(frozen=True)
class AttachmentDownload:
    content: bytes
    filename: str
    mime_type: str
    size_bytes: int


class AttachmentService:
    MAX_FILE_SIZE = (
        10 * 1024 * 1024
    )
    MAX_ATTACHMENTS_PER_REQUEST = 5

    MIME_BY_EXTENSION = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    ALLOWED_SCAN_RESULTS = {
        "CLEAN",
        "INFECTED",
        "FAILED",
    }

    @classmethod
    def _validate_actor(
        cls,
        actor,
    ):
        actor_id = getattr(
            actor,
            "pk",
            None,
        )

        if actor_id is None:
            raise AttachmentActorError(
                "Attachment operation requires "
                "an active persisted user."
            )

        user_model = get_user_model()

        persisted = (
            user_model.objects
            .filter(
                pk=actor_id,
                is_active=True,
            )
            .first()
        )

        if persisted is None:
            raise AttachmentActorError(
                "Attachment operation requires "
                "an active persisted user."
            )

        return persisted

    @classmethod
    def _validate_choice(
        cls,
        *,
        field_name: str,
        value: str,
    ) -> str:
        value = value.strip().upper()

        field = (
            RequestAttachment
            ._meta
            .get_field(field_name)
        )

        valid = {
            choice[0]
            for choice in field.choices
        }

        if value not in valid:
            raise ValueError(
                f"Invalid {field_name}: "
                f"{value}"
            )

        return value

    @classmethod
    def _detected_mime(
        cls,
        content: bytes,
    ) -> str | None:
        if content.startswith(
            b"%PDF-"
        ):
            return "application/pdf"

        if content.startswith(
            b"\xff\xd8\xff"
        ):
            return "image/jpeg"

        if content.startswith(
            b"\x89PNG\r\n\x1a\n"
        ):
            return "image/png"

        return None

    @classmethod
    def _validate_file(
        cls,
        *,
        filename: str,
        declared_mime: str,
        content: bytes,
    ) -> str:
        if not isinstance(
            content,
            bytes,
        ):
            raise TypeError(
                "content must be bytes."
            )

        size = len(content)

        if (
            size <= 0
            or size
            > cls.MAX_FILE_SIZE
        ):
            raise FileRejectedError(
                "File size is not allowed."
            )

        filename = filename.strip()

        if not filename:
            raise FileRejectedError(
                "Filename is required."
            )

        extension = (
            Path(filename)
            .suffix
            .lower()
        )

        expected_mime = (
            cls.MIME_BY_EXTENSION
            .get(extension)
        )

        if expected_mime is None:
            raise FileRejectedError(
                "File extension is not allowed."
            )

        declared_mime = (
            declared_mime
            .strip()
            .lower()
        )

        if declared_mime != expected_mime:
            raise FileRejectedError(
                "Declared MIME does not match "
                "the file extension."
            )

        detected = cls._detected_mime(
            content
        )

        if detected != expected_mime:
            raise FileRejectedError(
                "File content does not match "
                "the declared MIME."
            )

        return detected

    @classmethod
    def _validate_representative(
        cls,
        *,
        request: RightsRequest,
        representative: (
            SubjectRepresentative | None
        ),
    ):
        if representative is None:
            return None

        persisted = (
            SubjectRepresentative.objects
            .filter(
                pk=representative.pk,
                data_subject_id=(
                    request.data_subject_id
                ),
            )
            .first()
        )

        if persisted is None:
            raise FileRejectedError(
                "Representative does not "
                "belong to this request."
            )

        return persisted

    @classmethod
    def _scan(
        cls,
        *,
        scanner: MalwareScanner | None,
        content: bytes,
    ) -> str:
        if scanner is None:
            raise (
                MalwareScannerUnavailableError(
                    "Malware scanner is required."
                )
            )

        result = scanner.scan(
            content
        )

        result = (
            str(result)
            .strip()
            .upper()
        )

        if (
            result
            not in cls.ALLOWED_SCAN_RESULTS
        ):
            raise FileRejectedError(
                "Invalid malware scan result."
            )

        if result != "CLEAN":
            raise FileRejectedError(
                "File failed malware scanning."
            )

        return result

    @classmethod
    def create(
        cls,
        *,
        request: RightsRequest,
        attachment_type: str,
        visibility: str,
        filename: str,
        declared_mime: str,
        content: bytes,
        actor,
        scanner: MalwareScanner,
        representative: (
            SubjectRepresentative | None
        ) = None,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> RequestAttachment:
        actor = cls._validate_actor(
            actor
        )

        attachment_type = (
            cls._validate_choice(
                field_name=(
                    "attachment_type"
                ),
                value=attachment_type,
            )
        )

        visibility = cls._validate_choice(
            field_name="visibility",
            value=visibility,
        )

        detected_mime = (
            cls._validate_file(
                filename=filename,
                declared_mime=(
                    declared_mime
                ),
                content=content,
            )
        )

        scan_status = cls._scan(
            scanner=scanner,
            content=content,
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

        encryption_version = int(
            settings
            .PII_ENCRYPTION_ACTIVE_VERSION
        )

        attachment_id = uuid.uuid4()
        storage_key = (
            "attachments/"
            f"{request.id}/"
            f"{attachment_id}.bin"
        )

        filename_encrypted = (
            CryptoService.encrypt_text(
                filename.strip(),
                aad=(
                    "request_attachments:"
                    f"{attachment_id}:"
                    "original_filename"
                ),
                key_version=(
                    encryption_version
                ),
            )
        )

        file_sha256 = hashlib.sha256(
            content
        ).hexdigest()

        representative = (
            cls._validate_representative(
                request=request,
                representative=(
                    representative
                ),
            )
        )

        LocalPrivateStorageService \
            .write_encrypted(
                storage_key=storage_key,
                plaintext=content,
                key_version=(
                    encryption_version
                ),
            )

        try:
            with transaction.atomic():
                locked_request = (
                    RightsRequest.objects
                    .select_for_update()
                    .get(pk=request.pk)
                )

                active_count = (
                    RequestAttachment.objects
                    .filter(
                        request=locked_request,
                        deleted_at__isnull=True,
                    )
                    .count()
                )

                if (
                    active_count
                    >= cls.MAX_ATTACHMENTS_PER_REQUEST
                ):
                    raise AttachmentLimitError(
                        "Maximum attachments "
                        "per request reached."
                    )

                attachment = (
                    RequestAttachment.objects
                    .create(
                        id=attachment_id,
                        request=locked_request,
                        representative=(
                            representative
                        ),
                        attachment_type=(
                            attachment_type
                        ),
                        visibility=visibility,
                        original_filename_encrypted=(
                            filename_encrypted.data
                        ),
                        storage_backend=(
                            "LOCAL"
                        ),
                        storage_key=(
                            storage_key
                        ),
                        mime_type=(
                            detected_mime
                        ),
                        size_bytes=len(
                            content
                        ),
                        file_sha256=(
                            file_sha256
                        ),
                        is_encrypted=True,
                        encryption_key_version=(
                            encryption_version
                        ),
                        malware_scan_status=(
                            scan_status
                        ),
                        uploaded_by=actor,
                    )
                )

                AuditService.write(
                    actor_type=(
                        AuditLog.ActorType.USER
                    ),
                    actor=actor,
                    source=(
                        AuditLog.Source.WEB
                    ),
                    correlation_id=(
                        correlation_id
                    ),
                    action=(
                        "REQUEST_ATTACHMENT_CREATED"
                    ),
                    entity_type=(
                        "REQUEST_ATTACHMENT"
                    ),
                    entity_pk=(
                        attachment.id
                    ),
                    description=(
                        "Private request attachment "
                        "created."
                    ),
                    metadata={
                        "request_id": str(
                            locked_request.id
                        ),
                        "attachment_type": (
                            attachment_type
                        ),
                        "visibility": (
                            visibility
                        ),
                        "mime_type": (
                            detected_mime
                        ),
                        "size_bytes": (
                            len(content)
                        ),
                        "malware_scan_status": (
                            scan_status
                        ),
                    },
                )

                return attachment

        except Exception:
            LocalPrivateStorageService \
                .delete(
                    storage_key=storage_key
                )
            raise

    @classmethod
    def decrypt_filename(
        cls,
        attachment: RequestAttachment,
    ) -> str:
        return CryptoService.decrypt_text(
            attachment
            .original_filename_encrypted,
            aad=(
                "request_attachments:"
                f"{attachment.id}:"
                "original_filename"
            ),
            key_version=(
                attachment
                .encryption_key_version
            ),
        )

    @classmethod
    def download(
        cls,
        *,
        attachment: RequestAttachment,
        actor,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> AttachmentDownload:
        actor = cls._validate_actor(
            actor
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

        persisted = (
            RequestAttachment.objects
            .select_related("request")
            .filter(
                pk=attachment.pk,
                deleted_at__isnull=True,
            )
            .first()
        )

        if persisted is None:
            raise FileRejectedError(
                "Attachment is unavailable."
            )

        if (
            persisted
            .malware_scan_status
            != "CLEAN"
        ):
            raise FileRejectedError(
                "Attachment is not approved "
                "for download."
            )

        content = (
            LocalPrivateStorageService
            .read_encrypted(
                storage_key=(
                    persisted.storage_key
                ),
                key_version=(
                    persisted
                    .encryption_key_version
                ),
            )
        )

        calculated_hash = (
            hashlib.sha256(
                content
            ).hexdigest()
        )

        if calculated_hash != (
            persisted.file_sha256
        ):
            raise AttachmentIntegrityError(
                "Attachment integrity "
                "verification failed."
            )

        if len(content) != (
            persisted.size_bytes
        ):
            raise AttachmentIntegrityError(
                "Attachment size "
                "verification failed."
            )

        filename = cls.decrypt_filename(
            persisted
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
                "REQUEST_ATTACHMENT_DOWNLOADED"
            ),
            entity_type=(
                "REQUEST_ATTACHMENT"
            ),
            entity_pk=persisted.id,
            description=(
                "Private request attachment "
                "downloaded."
            ),
            metadata={
                "request_id": str(
                    persisted.request_id
                ),
                "attachment_type": (
                    persisted
                    .attachment_type
                ),
                "visibility": (
                    persisted.visibility
                ),
                "mime_type": (
                    persisted.mime_type
                ),
                "size_bytes": (
                    persisted.size_bytes
                ),
            },
        )

        return AttachmentDownload(
            content=content,
            filename=filename,
            mime_type=(
                persisted.mime_type
            ),
            size_bytes=(
                persisted.size_bytes
            ),
        )
