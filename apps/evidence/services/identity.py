from __future__ import annotations

import uuid

from django.conf import settings
from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services.audit import AuditService, LogSanitizer
from apps.cases.models import RightsRequest
from apps.cases.policies import (
    can_start_review,
    can_view_sensitive_case_data,
)
from apps.cases.services.cases import CaseWorkflowService
from apps.core.services.crypto import CryptoService
from apps.evidence.models import IdentityVerification


class IdentityVerificationError(Exception):
    pass


class IdentityVerificationPermissionError(IdentityVerificationError):
    pass


class IdentityVerificationStateError(IdentityVerificationError):
    pass


class IdentityVerificationService:
    RESULT_TO_IDENTITY_STATUS = {
        IdentityVerification.Result.PENDING: (
            RightsRequest.IdentityStatus.PENDING
        ),
        IdentityVerification.Result.VERIFIED: (
            RightsRequest.IdentityStatus.VERIFIED
        ),
        IdentityVerification.Result.REJECTED: (
            RightsRequest.IdentityStatus.REJECTED
        ),
        IdentityVerification.Result.INCONCLUSIVE: (
            RightsRequest.IdentityStatus.REQUIRES_REVIEW
        ),
    }

    TERMINAL_REQUEST_STATUSES = {
        RightsRequest.Status.RESPONDED,
        RightsRequest.Status.REJECTED,
        RightsRequest.Status.ARCHIVED,
        RightsRequest.Status.CANCELLED,
        RightsRequest.Status.CLOSED,
    }

    @classmethod
    def _normalize_choice(cls, *, value: str, choices, field_name: str) -> str:
        normalized = str(value).strip().upper()
        if normalized not in {choice[0] for choice in choices}:
            raise ValueError(f"Invalid {field_name}: {normalized}")
        return normalized

    @classmethod
    def _normalize_correlation_id(cls, correlation_id) -> uuid.UUID:
        if correlation_id is None:
            return uuid.uuid4()
        if isinstance(correlation_id, uuid.UUID):
            return correlation_id
        return uuid.UUID(str(correlation_id))

    @classmethod
    def _validate_actor(cls, *, actor, request: RightsRequest):
        actor = CaseWorkflowService._validate_actor(actor)
        if actor is None or not can_start_review(actor, request):
            raise IdentityVerificationPermissionError(
                "Identity verification is not permitted for this actor."
            )
        return actor

    @classmethod
    def _notes_aad(cls, verification_id: uuid.UUID) -> str:
        return (
            f"identity_verifications:{verification_id}:"
            "validation_notes"
        )

    @classmethod
    def record(
        cls,
        *,
        request: RightsRequest,
        verification_method: str,
        result: str,
        actor,
        validation_notes: str | None = None,
        validation_metadata: dict | None = None,
        source: str = AuditLog.Source.WEB,
        correlation_id: uuid.UUID | None = None,
    ) -> IdentityVerification:
        verification_method = cls._normalize_choice(
            value=verification_method,
            choices=IdentityVerification.VerificationMethod.choices,
            field_name="verification_method",
        )
        result = cls._normalize_choice(
            value=result,
            choices=IdentityVerification.Result.choices,
            field_name="result",
        )
        correlation_id = cls._normalize_correlation_id(correlation_id)

        if validation_metadata is not None and not isinstance(
            validation_metadata, dict
        ):
            raise TypeError("validation_metadata must be a dictionary.")

        safe_metadata = LogSanitizer.sanitize(validation_metadata or {})
        verification_id = uuid.uuid4()
        encryption_key_version = settings.PII_ENCRYPTION_ACTIVE_VERSION
        encrypted_notes = None

        if validation_notes is not None and validation_notes.strip():
            encrypted_notes = CryptoService.encrypt_text(
                validation_notes.strip(),
                aad=cls._notes_aad(verification_id),
                key_version=encryption_key_version,
            ).data

        with transaction.atomic():
            locked_request = RightsRequest.objects.select_for_update().get(
                pk=request.pk
            )
            actor = cls._validate_actor(
                actor=actor,
                request=locked_request,
            )

            if locked_request.status in cls.TERMINAL_REQUEST_STATUSES:
                raise IdentityVerificationStateError(
                    "Identity verification cannot modify a terminal request."
                )

            previous_status = locked_request.identity_status
            target_status = cls.RESULT_TO_IDENTITY_STATUS[result]

            verification = IdentityVerification.objects.create(
                id=verification_id,
                request=locked_request,
                verification_method=verification_method,
                result=result,
                validation_metadata=safe_metadata,
                validation_notes_encrypted=encrypted_notes,
                encryption_key_version=encryption_key_version,
                verified_by=actor,
                verified_at=CaseWorkflowService._database_now(),
            )

            if previous_status != target_status:
                locked_request.identity_status = target_status
                locked_request.save(
                    update_fields=["identity_status", "updated_at"]
                )

            AuditService.write(
                action="IDENTITY_VERIFICATION_RECORDED",
                entity_type="IdentityVerification",
                actor=actor,
                source=source,
                correlation_id=correlation_id,
                entity_pk=verification.id,
                description="Identity verification result recorded.",
                previous_values={"identity_status": previous_status},
                new_values={
                    "identity_status": target_status,
                    "verification_method": verification_method,
                    "result": result,
                },
                metadata={
                    "request_id": str(locked_request.id),
                    "has_encrypted_notes": encrypted_notes is not None,
                },
            )

        return verification

    @classmethod
    def decrypt_notes(cls, *, verification: IdentityVerification, actor) -> str | None:
        request = RightsRequest.objects.get(pk=verification.request_id)
        if not can_view_sensitive_case_data(actor, request):
            raise IdentityVerificationPermissionError(
                "Identity verification notes are not available to this actor."
            )
        if verification.validation_notes_encrypted is None:
            return None
        return CryptoService.decrypt_text(
            verification.validation_notes_encrypted,
            aad=cls._notes_aad(verification.id),
            key_version=verification.encryption_key_version,
        )
