from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService
from apps.cases.models import (
    RequestStatusHistory,
    RightsRequest,
)
from apps.core.services.crypto import CryptoService
from apps.legal_content.models import RightCatalog
from apps.organization.models import SystemSetting
from apps.subjects.models import (
    DataSubject,
    SubjectRepresentative,
)
from apps.subjects.services.subjects import (
    SubjectService,
)


class CaseWorkflowError(Exception):
    pass


class CaseConfigurationError(
    CaseWorkflowError
):
    pass


class CaseActorError(
    CaseWorkflowError
):
    pass


class InactiveRightError(
    CaseWorkflowError
):
    def __init__(self, right_id):
        self.right_id = right_id

        super().__init__(
            f"Right is not active: {right_id}"
        )


class RepresentativeSubjectMismatchError(
    CaseWorkflowError
):
    def __init__(
        self,
        *,
        representative_id,
        data_subject_id,
    ):
        self.representative_id = (
            representative_id
        )
        self.data_subject_id = (
            data_subject_id
        )

        super().__init__(
            "Representative does not belong "
            "to the supplied data subject."
        )


@dataclass(frozen=True)
class CaseSubjectSnapshot:
    subject_id: uuid.UUID
    subject_type: str
    document_type: str
    document_number: str
    full_name: str
    email: str
    phone: str | None


class CaseWorkflowService:
    @classmethod
    def _get_system_setting(
        cls,
    ) -> SystemSetting:
        setting = (
            SystemSetting.objects
            .filter(singleton_key=1)
            .first()
        )

        if setting is None:
            raise CaseConfigurationError(
                "SystemSetting singleton "
                "is required."
            )

        prefix = (
            setting.request_prefix
            or ""
        ).strip().upper()

        if not prefix:
            raise CaseConfigurationError(
                "request_prefix is required."
            )

        return setting

    @classmethod
    def _validate_actor(
        cls,
        actor,
    ):
        if actor is None:
            return None

        actor_id = getattr(
            actor,
            "pk",
            None,
        )

        if actor_id is None:
            raise CaseActorError(
                "Actor must be an active "
                "persisted user."
            )

        user_model = get_user_model()

        persisted_actor = (
            user_model.objects
            .filter(
                pk=actor_id,
                is_active=True,
            )
            .first()
        )

        if persisted_actor is None:
            raise CaseActorError(
                "Actor must be an active "
                "persisted user."
            )

        return persisted_actor

    @classmethod
    def _validate_source_channel(
        cls,
        source_channel: str,
    ) -> str:
        source_channel = (
            source_channel
            .strip()
            .upper()
        )

        valid_values = {
            choice[0]
            for choice in (
                RightsRequest
                .SourceChannel
                .choices
            )
        }

        if source_channel not in (
            valid_values
        ):
            raise ValueError(
                "Invalid source_channel: "
                f"{source_channel}"
            )

        return source_channel

    @classmethod
    def _validate_right(
        cls,
        right: RightCatalog,
    ) -> RightCatalog:
        persisted = (
            RightCatalog.objects
            .filter(
                pk=right.pk,
                is_active=True,
            )
            .first()
        )

        if persisted is None:
            raise InactiveRightError(
                getattr(
                    right,
                    "pk",
                    None,
                )
            )

        return persisted

    @classmethod
    def _validate_representative(
        cls,
        *,
        data_subject: DataSubject,
        representative: (
            SubjectRepresentative | None
        ),
    ) -> (
        SubjectRepresentative | None
    ):
        if representative is None:
            return None

        persisted = (
            SubjectRepresentative.objects
            .filter(
                pk=representative.pk,
                data_subject_id=(
                    data_subject.pk
                ),
            )
            .first()
        )

        if persisted is None:
            raise (
                RepresentativeSubjectMismatchError(
                    representative_id=(
                        getattr(
                            representative,
                            "pk",
                            None,
                        )
                    ),
                    data_subject_id=(
                        data_subject.pk
                    ),
                )
            )

        return persisted

    @classmethod
    def _next_reference(
        cls,
        *,
        system_setting: SystemSetting,
    ) -> tuple[str, object]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "nextval('rights_request_seq'), "
                "transaction_timestamp()"
            )

            row = cursor.fetchone()

        sequence_value = int(row[0])
        db_now = row[1]

        try:
            local_now = db_now.astimezone(
                ZoneInfo(
                    system_setting.timezone
                )
            )
        except Exception as exc:
            raise CaseConfigurationError(
                "Invalid system timezone: "
                f"{system_setting.timezone}"
            ) from exc

        prefix = (
            system_setting
            .request_prefix
            .strip()
            .upper()
        )

        reference_number = (
            f"{prefix}-"
            f"{local_now.year}-"
            f"{sequence_value:06d}"
        )

        if len(reference_number) > 50:
            raise CaseConfigurationError(
                "Generated reference_number "
                "exceeds 50 characters."
            )

        return reference_number, db_now

    @classmethod
    def _subject_snapshot_payload(
        cls,
        data_subject: DataSubject,
    ) -> dict:
        pii = SubjectService.decrypt(
            data_subject
        )

        return {
            "subject_id": str(pii.id),
            "subject_type": (
                pii.subject_type
            ),
            "document_type": (
                pii.document_type
            ),
            "document_number": (
                pii.document_number
            ),
            "full_name": pii.full_name,
            "email": pii.email,
            "phone": pii.phone,
        }

    @classmethod
    def _encrypt_request_details(
        cls,
        *,
        request_id: uuid.UUID,
        request_details: str,
        key_version: int,
    ) -> bytes:
        request_details = (
            request_details.strip()
        )

        if not request_details:
            raise ValueError(
                "request_details is required."
            )

        encrypted = (
            CryptoService.encrypt_text(
                request_details,
                aad=(
                    f"rights_requests:"
                    f"{request_id}:"
                    f"request_details"
                ),
                key_version=key_version,
            )
        )

        return encrypted.data

    @classmethod
    def _encrypt_subject_snapshot(
        cls,
        *,
        request_id: uuid.UUID,
        snapshot: dict,
        key_version: int,
    ) -> bytes:
        serialized = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        encrypted = (
            CryptoService.encrypt_text(
                serialized,
                aad=(
                    f"rights_requests:"
                    f"{request_id}:"
                    f"subject_snapshot"
                ),
                key_version=key_version,
            )
        )

        return encrypted.data

    @classmethod
    def _history_source_for_channel(
        cls,
        source_channel: str,
    ) -> str:
        if (
            source_channel
            == RightsRequest
            .SourceChannel
            .WEB
        ):
            return (
                RequestStatusHistory
                .ChangeSource
                .WEB
            )

        return (
            RequestStatusHistory
            .ChangeSource
            .SYSTEM
        )

    @classmethod
    def create_request(
        cls,
        *,
        data_subject: DataSubject,
        right: RightCatalog,
        request_details: str,
        representative: (
            SubjectRepresentative | None
        ) = None,
        source_channel: str = (
            RightsRequest
            .SourceChannel
            .WEB
        ),
        actor=None,
        correlation_id: (
            uuid.UUID | None
        ) = None,
    ) -> RightsRequest:
        actor = cls._validate_actor(
            actor
        )

        source_channel = (
            cls._validate_source_channel(
                source_channel
            )
        )

        right = cls._validate_right(
            right
        )

        representative = (
            cls._validate_representative(
                data_subject=data_subject,
                representative=(
                    representative
                ),
            )
        )

        system_setting = (
            cls._get_system_setting()
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

        request_id = uuid.uuid4()

        encryption_key_version = (
            settings
            .PII_ENCRYPTION_ACTIVE_VERSION
        )

        snapshot = (
            cls._subject_snapshot_payload(
                data_subject
            )
        )

        request_details_encrypted = (
            cls._encrypt_request_details(
                request_id=request_id,
                request_details=(
                    request_details
                ),
                key_version=(
                    encryption_key_version
                ),
            )
        )

        snapshot_encrypted = (
            cls._encrypt_subject_snapshot(
                request_id=request_id,
                snapshot=snapshot,
                key_version=(
                    encryption_key_version
                ),
            )
        )

        with transaction.atomic():
            (
                reference_number,
                db_now,
            ) = cls._next_reference(
                system_setting=(
                    system_setting
                )
            )

            request = (
                RightsRequest.objects.create(
                    id=request_id,
                    data_subject=(
                        data_subject
                    ),
                    representative=(
                        representative
                    ),
                    right=right,
                    reference_number=(
                        reference_number
                    ),
                    request_details_encrypted=(
                        request_details_encrypted
                    ),
                    subject_snapshot_encrypted=(
                        snapshot_encrypted
                    ),
                    encryption_key_version=(
                        encryption_key_version
                    ),
                    snapshot_key_version=(
                        encryption_key_version
                    ),
                    source_channel=(
                        source_channel
                    ),
                    status=(
                        RightsRequest
                        .Status
                        .RECEIVED
                    ),
                    identity_status=(
                        RightsRequest
                        .IdentityStatus
                        .PENDING
                    ),
                    received_at=db_now,
                    created_at=db_now,
                    updated_at=db_now,
                )
            )

            RequestStatusHistory.objects.create(
                request=request,
                previous_status=None,
                new_status=(
                    RightsRequest
                    .Status
                    .RECEIVED
                ),
                encryption_key_version=(
                    encryption_key_version
                ),
                changed_by=actor,
                change_source=(
                    cls
                    ._history_source_for_channel(
                        source_channel
                    )
                ),
                changed_at=db_now,
            )

            AuditService.write(
                actor_type=(
                    AuditLog.ActorType.USER
                    if actor is not None
                    else AuditLog.ActorType.SYSTEM
                ),
                actor=actor,
                source=(
                    AuditLog.Source.WEB
                    if (
                        source_channel
                        == RightsRequest
                        .SourceChannel
                        .WEB
                    )
                    else AuditLog.Source.SYSTEM
                ),
                correlation_id=(
                    correlation_id
                ),
                action=(
                    "RIGHTS_REQUEST_CREATED"
                ),
                entity_type=(
                    "RIGHTS_REQUEST"
                ),
                entity_pk=request.id,
                description=(
                    "Rights request created."
                ),
                metadata={
                    "reference_number": (
                        request.reference_number
                    ),
                    "source_channel": (
                        source_channel
                    ),
                    "right_code": right.code,
                    "representative_used": (
                        representative
                        is not None
                    ),
                },
            )

            return request

    @classmethod
    def decrypt_request_details(
        cls,
        request: RightsRequest,
    ) -> str:
        return CryptoService.decrypt_text(
            request.request_details_encrypted,
            aad=(
                f"rights_requests:"
                f"{request.id}:"
                f"request_details"
            ),
            key_version=(
                request
                .encryption_key_version
            ),
        )

    @classmethod
    def decrypt_subject_snapshot(
        cls,
        request: RightsRequest,
    ) -> CaseSubjectSnapshot:
        serialized = (
            CryptoService.decrypt_text(
                request
                .subject_snapshot_encrypted,
                aad=(
                    f"rights_requests:"
                    f"{request.id}:"
                    f"subject_snapshot"
                ),
                key_version=(
                    request
                    .snapshot_key_version
                ),
            )
        )

        payload = json.loads(
            serialized
        )

        return CaseSubjectSnapshot(
            subject_id=uuid.UUID(
                payload["subject_id"]
            ),
            subject_type=(
                payload["subject_type"]
            ),
            document_type=(
                payload["document_type"]
            ),
            document_number=(
                payload["document_number"]
            ),
            full_name=(
                payload["full_name"]
            ),
            email=payload["email"],
            phone=payload.get(
                "phone"
            ),
        )
