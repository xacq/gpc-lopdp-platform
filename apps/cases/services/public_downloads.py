from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import (
    RequestAccessToken,
    RightsRequest,
)
from apps.cases.services.tokens import (
    RequestAccessTokenService,
    TokenInvalidOrExpiredError,
)
from apps.core.services.storage import (
    LocalPrivateStorageService,
)
from apps.evidence.models import (
    RequestAttachment,
)
from apps.evidence.services.attachments import (
    AttachmentIntegrityError,
    AttachmentService,
)


class PublicDownloadError(Exception):
    pass


class PublicDownloadAccessError(
    PublicDownloadError
):
    """
    Generic public-facing access error.

    Do not reveal whether the reference, attachment,
    visibility, token, binding, expiry, or revocation
    check failed.
    """

    pass


@dataclass(frozen=True)
class PublicAttachmentDownload:
    content: bytes
    filename: str
    mime_type: str
    size_bytes: int


class PublicDownloadService:
    @classmethod
    def _normalize_reference(
        cls,
        reference_number: str,
    ) -> str:
        if not isinstance(
            reference_number,
            str,
        ):
            raise PublicDownloadAccessError()

        reference_number = (
            reference_number
            .strip()
            .upper()
        )

        if not reference_number:
            raise PublicDownloadAccessError()

        return reference_number

    @classmethod
    def _normalize_uuid(
        cls,
        value,
    ) -> uuid.UUID:
        if isinstance(
            value,
            uuid.UUID,
        ):
            return value

        try:
            return uuid.UUID(
                str(value)
            )
        except (
            TypeError,
            ValueError,
            AttributeError,
        ) as exc:
            raise (
                PublicDownloadAccessError()
            ) from exc

    @classmethod
    def _normalize_correlation_id(
        cls,
        value,
    ) -> uuid.UUID:
        if value is None:
            return uuid.uuid4()

        if isinstance(
            value,
            uuid.UUID,
        ):
            return value

        return uuid.UUID(
            str(value)
        )

    @classmethod
    def download_attachment(
        cls,
        *,
        reference_number: str,
        attachment_id,
        token: str,
        correlation_id=None,
    ) -> PublicAttachmentDownload:
        reference_number = (
            cls._normalize_reference(
                reference_number
            )
        )

        attachment_id = (
            cls._normalize_uuid(
                attachment_id
            )
        )

        correlation_id = (
            cls._normalize_correlation_id(
                correlation_id
            )
        )

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
            raise PublicDownloadAccessError()

        attachment = (
            RequestAttachment.objects
            .filter(
                pk=attachment_id,
                request=request,
                visibility="SUBJECT",
                deleted_at__isnull=True,
                malware_scan_status="CLEAN",
            )
            .first()
        )

        if attachment is None:
            raise PublicDownloadAccessError()

        try:
            (
                RequestAccessTokenService
                .validate(
                    request=request,
                    token=token,
                    purpose=(
                        RequestAccessToken
                        .Purpose
                        .FILE_DOWNLOAD
                    ),
                    resource_type=(
                        RequestAccessToken
                        .ResourceType
                        .ATTACHMENT
                    ),
                    resource_id=(
                        attachment.id
                    ),
                )
            )
        except (
            TokenInvalidOrExpiredError
        ) as exc:
            raise PublicDownloadAccessError() from exc

        content = (
            LocalPrivateStorageService
            .read_encrypted(
                storage_key=(
                    attachment.storage_key
                ),
                key_version=(
                    attachment
                    .encryption_key_version
                ),
            )
        )

        if (
            hashlib.sha256(
                content
            ).hexdigest()
            != attachment.file_sha256
        ):
            raise AttachmentIntegrityError(
                "Attachment integrity "
                "verification failed."
            )

        if (
            len(content)
            != attachment.size_bytes
        ):
            raise AttachmentIntegrityError(
                "Attachment size "
                "verification failed."
            )

        filename = (
            AttachmentService
            .decrypt_filename(
                attachment
            )
        )

        try:
            with transaction.atomic():
                consumed = (
                    RequestAccessTokenService
                    .consume(
                        request=request,
                        token=token,
                        purpose=(
                            RequestAccessToken
                            .Purpose
                            .FILE_DOWNLOAD
                        ),
                        resource_type=(
                            RequestAccessToken
                            .ResourceType
                            .ATTACHMENT
                        ),
                        resource_id=(
                            attachment.id
                        ),
                        actor=None,
                        correlation_id=(
                            correlation_id
                        ),
                        source=(
                            AuditLog.Source.WEB
                        ),
                    )
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
                        "PUBLIC_ATTACHMENT_DOWNLOADED"
                    ),
                    entity_type=(
                        "REQUEST_ATTACHMENT"
                    ),
                    entity_pk=(
                        attachment.id
                    ),
                    description=(
                        "Subject-visible attachment "
                        "downloaded through public "
                        "token access."
                    ),
                    metadata={
                        "request_id": str(
                            request.id
                        ),
                        "attachment_id": str(
                            attachment.id
                        ),
                        "token_id": str(
                            consumed.id
                        ),
                        "mime_type": (
                            attachment.mime_type
                        ),
                        "size_bytes": (
                            attachment.size_bytes
                        ),
                    },
                )

        except (
            TokenInvalidOrExpiredError
        ) as exc:
            raise PublicDownloadAccessError() from exc

        return PublicAttachmentDownload(
            content=content,
            filename=filename,
            mime_type=(
                attachment.mime_type
            ),
            size_bytes=(
                attachment.size_bytes
            ),
        )
